"""IntentOS Speech-to-Text module.

Primary backend: faster-whisper (local, MIT, runs on CPU/GPU).
Fallback: speech_recognition + Google free API.

All backends are lazy-loaded — missing dependencies degrade gracefully.
"""

from __future__ import annotations

import enum
import os
import tempfile
import time
import wave
from dataclasses import dataclass
from typing import Any, Optional


# ---------------------------------------------------------------------------
# STTProvider enum
# ---------------------------------------------------------------------------

class STTProvider(enum.Enum):
    """Available speech-to-text backends."""
    FASTER_WHISPER = "faster_whisper"    # Local Whisper via faster-whisper
    SYSTEM = "system"                    # Google free API via speech_recognition
    OPENAI_WHISPER_API = "openai_whisper_api"  # OpenAI Whisper API
    GOOGLE_CLOUD = "google_cloud"        # Google Cloud Speech API


# ---------------------------------------------------------------------------
# STTResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class STTResult:
    """Result of a speech-to-text transcription."""
    text: str
    confidence: float = 0.0
    provider: str = ""
    duration_seconds: float = 0.0
    language: str = "en"


# ---------------------------------------------------------------------------
# VoiceInput
# ---------------------------------------------------------------------------

# Whisper model cache (loaded once, reused)
_whisper_model = None
_whisper_model_name = None


class VoiceInput:
    """Speech-to-text input for IntentOS.

    Primary: faster-whisper with large-v3-turbo (best quality/speed).
    Fallback: speech_recognition + Google free API.
    """

    def __init__(
        self,
        provider: STTProvider = STTProvider.FASTER_WHISPER,
        model_size: str = "large-v3-turbo",
    ) -> None:
        self._provider = provider
        self._model_size = model_size

    # -- availability -------------------------------------------------------

    def is_available(self) -> bool:
        """Check whether voice input is usable."""
        if self._provider == STTProvider.FASTER_WHISPER:
            try:
                from faster_whisper import WhisperModel  # noqa: F401
                return True
            except ImportError:
                pass

        # Fall back to checking speech_recognition
        try:
            import speech_recognition as sr
            sr.Microphone()
            return True
        except (ImportError, OSError, AttributeError):
            return False

    def get_best_available(self) -> STTProvider:
        """Return the best available provider."""
        try:
            from faster_whisper import WhisperModel  # noqa: F401
            return STTProvider.FASTER_WHISPER
        except ImportError:
            pass

        try:
            import speech_recognition as sr
            sr.Microphone()
            return STTProvider.SYSTEM
        except (ImportError, OSError):
            pass

        return STTProvider.SYSTEM

    # -- recording ----------------------------------------------------------

    def record(self, duration_seconds: float = 5) -> Optional[str]:
        """Record audio from microphone, save to temp WAV file.

        Returns the path to the WAV file, or None on failure.
        """
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(
                    source,
                    timeout=duration_seconds,
                    phrase_time_limit=duration_seconds,
                )

            # Save to temp file
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(audio.get_wav_data())
            tmp.close()
            return tmp.name
        except Exception:
            return None

    # -- transcription ------------------------------------------------------

    def transcribe_file(
        self,
        audio_path: str,
        provider: Optional[STTProvider] = None,
    ) -> Optional[STTResult]:
        """Transcribe an audio file using the specified provider."""
        provider = provider or self._provider
        start = time.monotonic()

        if provider == STTProvider.FASTER_WHISPER:
            result = self._transcribe_faster_whisper(audio_path, start)
            if result:
                return result
            # Fall through to system
            provider = STTProvider.SYSTEM

        if provider == STTProvider.SYSTEM:
            return self._transcribe_system(audio_path, start)

        if provider == STTProvider.OPENAI_WHISPER_API:
            return self._transcribe_openai_whisper(audio_path, start)

        return None

    def _transcribe_faster_whisper(
        self, audio_path: str, start: float,
    ) -> Optional[STTResult]:
        """Transcribe using faster-whisper (local, fast, high quality)."""
        global _whisper_model, _whisper_model_name

        try:
            from faster_whisper import WhisperModel

            # Load model (cached after first use)
            if _whisper_model is None or _whisper_model_name != self._model_size:
                _whisper_model = WhisperModel(
                    self._model_size,
                    device="auto",
                    compute_type="auto",
                )
                _whisper_model_name = self._model_size

            segments, info = _whisper_model.transcribe(
                audio_path,
                beam_size=5,
                language="en",
                vad_filter=True,
            )

            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            text = " ".join(text_parts)
            duration = time.monotonic() - start

            return STTResult(
                text=text,
                confidence=round(info.language_probability, 2) if info else 0.9,
                provider="faster_whisper",
                duration_seconds=round(duration, 2),
                language=info.language if info else "en",
            )
        except ImportError:
            return None
        except Exception:
            return None

    def _transcribe_system(
        self, audio_path: str, start: float,
    ) -> Optional[STTResult]:
        """Transcribe using Google free API via speech_recognition."""
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            with sr.AudioFile(audio_path) as source:
                audio = recognizer.record(source)

            text = recognizer.recognize_google(audio)
            duration = time.monotonic() - start

            return STTResult(
                text=text,
                confidence=0.85,
                provider="system",
                duration_seconds=round(duration, 2),
                language="en",
            )
        except Exception:
            return None

    def _transcribe_openai_whisper(
        self, audio_path: str, start: float,
    ) -> Optional[STTResult]:
        """Transcribe via OpenAI Whisper API."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        try:
            import requests
            with open(audio_path, "rb") as f:
                resp = requests.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": ("audio.wav", f, "audio/wav")},
                    data={"model": "whisper-1"},
                    timeout=30,
                )
            if resp.status_code == 200:
                data = resp.json()
                duration = time.monotonic() - start
                return STTResult(
                    text=data.get("text", ""),
                    confidence=0.95,
                    provider="openai_whisper_api",
                    duration_seconds=round(duration, 2),
                    language="en",
                )
        except Exception:
            pass
        return None

    # -- convenience --------------------------------------------------------

    def listen_and_transcribe(
        self,
        duration: float = 5,
        provider: Optional[STTProvider] = None,
    ) -> Optional[STTResult]:
        """Record from microphone and transcribe in one call."""
        audio_path = self.record(duration_seconds=duration)
        if audio_path is None:
            return None

        try:
            result = self.transcribe_file(audio_path, provider=provider)
            return result
        finally:
            # Cleanup temp file
            try:
                os.unlink(audio_path)
            except OSError:
                pass

    def voice_prompt(self) -> Optional[str]:
        """Interactive voice prompt for CLI use."""
        if not self.is_available():
            print("  Voice input not available. Install: pip install faster-whisper SpeechRecognition pyaudio")
            return None

        print("  Listening... (speak now)")
        result = self.listen_and_transcribe(duration=5)
        if result and result.text:
            return result.text

        print("  Could not understand audio.")
        return None
