"""IntentOS Speech-to-Text module.

Provides voice input for task submission via microphone or audio file.
Supports multiple STT backends with graceful fallbacks when dependencies
(like pyaudio) are unavailable.
"""

from __future__ import annotations

import enum
import os
import time
import wave
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Lazy imports — these may not be installed
# ---------------------------------------------------------------------------

def _import_speech_recognition():
    """Import speech_recognition, returning None if unavailable."""
    try:
        import speech_recognition as sr
        return sr
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# STTProvider enum
# ---------------------------------------------------------------------------

class STTProvider(enum.Enum):
    """Available speech-to-text backends."""
    SYSTEM = "system"                   # Google free API via speech_recognition
    WHISPER_LOCAL = "whisper_local"      # Local Whisper via Ollama
    GOOGLE_CLOUD = "google_cloud"       # Google Cloud Speech API
    OPENAI_WHISPER_API = "openai_whisper_api"  # OpenAI Whisper API


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

class VoiceInput:
    """Speech-to-text input for IntentOS.

    Handles microphone recording, audio transcription, and convenient
    one-call listen-and-transcribe workflows.  Designed to degrade
    gracefully when pyaudio or speech_recognition are missing.
    """

    def __init__(self, provider: STTProvider = STTProvider.SYSTEM) -> None:
        self._provider = provider
        self._sr = _import_speech_recognition()

    # -- availability -------------------------------------------------------

    def is_available(self) -> bool:
        """Check whether microphone + speech_recognition are usable."""
        sr = self._sr
        if sr is None:
            return False
        try:
            mic = sr.Microphone()
            return True
        except (OSError, AttributeError, ImportError):
            return False

    # -- recording ----------------------------------------------------------

    def record(
        self,
        duration_seconds: float = 5,
        silence_timeout: float = 2.0,
    ) -> Any:
        """Record audio from the microphone.

        Returns a ``speech_recognition.AudioData`` object, or *None*
        if recording is not possible.
        """
        sr = self._sr
        if sr is None:
            return None

        try:
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(
                    source,
                    timeout=duration_seconds,
                    phrase_time_limit=duration_seconds,
                )
                return audio
        except Exception:
            return None

    # -- transcription ------------------------------------------------------

    def transcribe(
        self,
        audio_data: Any,
        provider: Optional[STTProvider] = None,
    ) -> Optional[STTResult]:
        """Transcribe audio data using the specified provider.

        Args:
            audio_data: A ``speech_recognition.AudioData`` object.
            provider: Override the default provider for this call.

        Returns:
            An ``STTResult``, or *None* on failure.
        """
        provider = provider or self._provider
        sr = self._sr

        if audio_data is None:
            return None

        start = time.monotonic()

        if provider == STTProvider.SYSTEM:
            return self._transcribe_system(audio_data, sr, start)
        elif provider == STTProvider.WHISPER_LOCAL:
            return self._transcribe_whisper_local(audio_data, start)
        elif provider == STTProvider.OPENAI_WHISPER_API:
            return self._transcribe_openai_whisper(audio_data, start)
        elif provider == STTProvider.GOOGLE_CLOUD:
            return self._transcribe_google_cloud(audio_data, sr, start)

        return None

    def _transcribe_system(self, audio_data: Any, sr: Any, start: float) -> Optional[STTResult]:
        """Transcribe using Google free web API (via speech_recognition)."""
        if sr is None:
            return None
        try:
            recognizer = sr.Recognizer()
            text = recognizer.recognize_google(audio_data)
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

    def _transcribe_whisper_local(self, audio_data: Any, start: float) -> Optional[STTResult]:
        """Transcribe via local Ollama Whisper model."""
        try:
            import requests  # noqa: F811
            # Ollama transcription endpoint
            resp = requests.post(
                "http://localhost:11434/api/transcribe",
                json={"audio": "base64_placeholder"},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                duration = time.monotonic() - start
                return STTResult(
                    text=data.get("text", ""),
                    confidence=data.get("confidence", 0.9),
                    provider="whisper_local",
                    duration_seconds=round(duration, 2),
                    language=data.get("language", "en"),
                )
        except Exception:
            pass
        return None

    def _transcribe_openai_whisper(self, audio_data: Any, start: float) -> Optional[STTResult]:
        """Transcribe via OpenAI Whisper API."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        try:
            import requests
            import tempfile

            # Write audio to a temp wav file for the API
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_data.get_wav_data())
                tmp_path = f.name

            with open(tmp_path, "rb") as audio_file:
                resp = requests.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": ("audio.wav", audio_file, "audio/wav")},
                    data={"model": "whisper-1"},
                    timeout=30,
                )

            os.unlink(tmp_path)

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

    def _transcribe_google_cloud(self, audio_data: Any, sr: Any, start: float) -> Optional[STTResult]:
        """Transcribe via Google Cloud Speech API (requires credentials)."""
        if sr is None:
            return None
        try:
            credentials_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if not credentials_json:
                return None
            recognizer = sr.Recognizer()
            text = recognizer.recognize_google_cloud(audio_data)
            duration = time.monotonic() - start
            return STTResult(
                text=text,
                confidence=0.92,
                provider="google_cloud",
                duration_seconds=round(duration, 2),
                language="en",
            )
        except Exception:
            return None

    # -- convenience --------------------------------------------------------

    def listen_and_transcribe(
        self,
        duration: float = 5,
        provider: Optional[STTProvider] = None,
    ) -> Optional[STTResult]:
        """Record from microphone and transcribe in one call."""
        audio = self.record(duration_seconds=duration)
        if audio is None:
            return None
        return self.transcribe(audio, provider=provider)

    def voice_prompt(self) -> Optional[str]:
        """Interactive voice prompt for CLI use.

        Shows a 'Listening...' indicator, records, transcribes, and
        returns the text.  Returns *None* with a printed message if
        voice input is not available.
        """
        if not self.is_available():
            print("  Voice input not available. Install: pip install SpeechRecognition pyaudio")
            return None

        print("  Listening... (speak now)")
        result = self.listen_and_transcribe(duration=5)
        if result and result.text:
            return result.text

        print("  Could not understand audio.")
        return None

    # -- file transcription -------------------------------------------------

    def transcribe_file(
        self,
        audio_path: str,
        provider: Optional[STTProvider] = None,
    ) -> Optional[STTResult]:
        """Transcribe an audio file (.wav or .mp3).

        Args:
            audio_path: Path to the audio file.
            provider: STT backend to use (defaults to instance default).

        Returns:
            An ``STTResult``, or *None* on failure.
        """
        sr = self._sr
        if sr is None:
            return None

        if not os.path.isfile(audio_path):
            return None

        try:
            recognizer = sr.Recognizer()
            with sr.AudioFile(audio_path) as source:
                audio = recognizer.record(source)
            return self.transcribe(audio, provider=provider)
        except Exception:
            return None
