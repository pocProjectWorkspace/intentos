"""IntentOS Text-to-Speech module.

Primary backend: Piper TTS (local, MIT, <100MB RAM, instant).
Fallback: system TTS (pyttsx3) or no-op.

All backends are lazy-loaded — missing dependencies degrade gracefully.
"""

from __future__ import annotations

import enum
import os
import struct
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# TTSProvider enum
# ---------------------------------------------------------------------------

class TTSProvider(enum.Enum):
    """Available text-to-speech backends."""
    PIPER = "piper"               # Piper TTS (local, fast, MIT)
    SYSTEM = "system"             # pyttsx3 / OS native
    SAY = "say"                   # macOS 'say' command
    NONE = "none"                 # No TTS (text only)


# ---------------------------------------------------------------------------
# TTSResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class TTSResult:
    """Result of a text-to-speech synthesis."""
    audio_path: str
    text: str
    duration_seconds: float
    provider: str
    sample_rate: int = 22050


# ---------------------------------------------------------------------------
# Piper voice model management
# ---------------------------------------------------------------------------

_PIPER_VOICE_DEFAULT = "en_US-lessac-medium"
_PIPER_MODELS_DIR = os.path.join(os.path.expanduser("~"), ".intentos", "tts_models")


def _ensure_piper_voice(voice_name: str = _PIPER_VOICE_DEFAULT) -> Optional[str]:
    """Download a Piper voice model if not present. Returns model path or None."""
    os.makedirs(_PIPER_MODELS_DIR, exist_ok=True)
    model_path = os.path.join(_PIPER_MODELS_DIR, f"{voice_name}.onnx")
    config_path = os.path.join(_PIPER_MODELS_DIR, f"{voice_name}.onnx.json")

    if os.path.exists(model_path) and os.path.exists(config_path):
        return model_path

    # Download from Piper's HuggingFace repository
    base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    # Voice path structure: en/en_US/lessac/medium/
    # Voice name format: en_US-lessac-medium → lang=en, locale=en_US, speaker=lessac, quality=medium
    parts = voice_name.split("-")
    if len(parts) >= 3:
        locale = parts[0]                               # "en_US"
        lang = locale.split("_")[0]                      # "en"
        speaker = parts[1]                               # "lessac"
        quality = parts[2] if len(parts) > 2 else "medium"  # "medium"

        model_url = f"{base_url}/{lang}/{locale}/{speaker}/{quality}/{voice_name}.onnx"
        config_url = f"{base_url}/{lang}/{locale}/{speaker}/{quality}/{voice_name}.onnx.json"
    else:
        return None

    try:
        import urllib.request
        print(f"  Downloading voice model: {voice_name}...")
        urllib.request.urlretrieve(model_url, model_path)
        urllib.request.urlretrieve(config_url, config_path)
        print(f"  Voice model ready.")
        return model_path
    except Exception as e:
        # Clean up partial downloads
        for p in (model_path, config_path):
            if os.path.exists(p):
                os.unlink(p)
        return None


# ---------------------------------------------------------------------------
# VoiceOutput
# ---------------------------------------------------------------------------

# Piper voice cache
_piper_voice = None
_piper_voice_name = None


class VoiceOutput:
    """Text-to-speech output for IntentOS.

    Primary: Piper TTS (MIT, local, <100MB RAM, instant synthesis).
    Fallback: macOS 'say' command, then pyttsx3, then none.
    """

    def __init__(
        self,
        provider: TTSProvider = TTSProvider.PIPER,
        voice: str = _PIPER_VOICE_DEFAULT,
    ) -> None:
        self._provider = provider
        self._voice = voice
        self._output_dir = os.path.join(
            os.path.expanduser("~"), ".intentos", "cache", "tts"
        )
        os.makedirs(self._output_dir, exist_ok=True)

    # -- availability -------------------------------------------------------

    def get_best_available(self) -> TTSProvider:
        """Return the best available TTS provider."""
        try:
            from piper import PiperVoice  # noqa: F401
            return TTSProvider.PIPER
        except ImportError:
            pass

        # macOS say command
        if os.path.exists("/usr/bin/say"):
            return TTSProvider.SAY

        try:
            import pyttsx3  # noqa: F401
            return TTSProvider.SYSTEM
        except ImportError:
            pass

        return TTSProvider.NONE

    # -- synthesis ----------------------------------------------------------

    def speak(
        self,
        text: str,
        provider: Optional[TTSProvider] = None,
    ) -> Optional[TTSResult]:
        """Synthesize speech from text, save to file.

        Returns TTSResult with the audio file path, or None on failure.
        """
        provider = provider or self._provider
        start = time.monotonic()

        if provider == TTSProvider.PIPER:
            result = self._speak_piper(text, start)
            if result:
                return result
            # Fall through

        if provider in (TTSProvider.SAY, TTSProvider.PIPER):
            if os.path.exists("/usr/bin/say"):
                return self._speak_say(text, start)

        if provider == TTSProvider.SYSTEM:
            return self._speak_system(text, start)

        return None

    def speak_and_play(
        self,
        text: str,
        provider: Optional[TTSProvider] = None,
    ) -> Optional[TTSResult]:
        """Synthesize and immediately play the audio."""
        result = self.speak(text, provider=provider)
        if result and result.audio_path:
            self.play_audio(result.audio_path)
        return result

    @staticmethod
    def play_audio(path: str) -> None:
        """Play an audio file using the system player."""
        try:
            if os.path.exists("/usr/bin/afplay"):
                # macOS
                subprocess.run(
                    ["afplay", path],
                    capture_output=True, timeout=30,
                )
            elif os.path.exists("/usr/bin/aplay"):
                # Linux
                subprocess.run(
                    ["aplay", path],
                    capture_output=True, timeout=30,
                )
        except Exception:
            pass

    # -- Piper backend ------------------------------------------------------

    def _speak_piper(self, text: str, start: float) -> Optional[TTSResult]:
        """Synthesize using Piper TTS (local, fast, high quality)."""
        global _piper_voice, _piper_voice_name

        try:
            from piper import PiperVoice

            # Ensure voice model is downloaded
            model_path = _ensure_piper_voice(self._voice)
            if model_path is None:
                return None

            # Load voice (cached)
            if _piper_voice is None or _piper_voice_name != self._voice:
                _piper_voice = PiperVoice.load(model_path)
                _piper_voice_name = self._voice

            # Synthesize
            output_path = os.path.join(
                self._output_dir, f"tts_{int(time.time())}.wav"
            )

            with wave.open(output_path, "wb") as wav_file:
                _piper_voice.synthesize(text, wav_file)

            # Get duration
            duration = 0.0
            try:
                with wave.open(output_path, "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    duration = frames / rate if rate else 0.0
            except Exception:
                duration = time.monotonic() - start

            return TTSResult(
                audio_path=output_path,
                text=text,
                duration_seconds=round(duration, 2),
                provider="piper",
                sample_rate=22050,
            )
        except ImportError:
            return None
        except Exception:
            return None

    # -- macOS say backend --------------------------------------------------

    def _speak_say(self, text: str, start: float) -> Optional[TTSResult]:
        """Synthesize using macOS 'say' command."""
        try:
            output_path = os.path.join(
                self._output_dir, f"tts_{int(time.time())}.aiff"
            )
            subprocess.run(
                ["say", "-o", output_path, text],
                capture_output=True, timeout=30,
            )
            duration = time.monotonic() - start
            return TTSResult(
                audio_path=output_path,
                text=text,
                duration_seconds=round(duration, 2),
                provider="say",
            )
        except Exception:
            return None

    # -- pyttsx3 backend ----------------------------------------------------

    def _speak_system(self, text: str, start: float) -> Optional[TTSResult]:
        """Synthesize using pyttsx3 (cross-platform, basic quality)."""
        try:
            import pyttsx3

            output_path = os.path.join(
                self._output_dir, f"tts_{int(time.time())}.wav"
            )

            engine = pyttsx3.init()
            engine.save_to_file(text, output_path)
            engine.runAndWait()

            duration = time.monotonic() - start
            return TTSResult(
                audio_path=output_path,
                text=text,
                duration_seconds=round(duration, 2),
                provider="system",
            )
        except Exception:
            return None
