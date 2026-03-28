"""Tests for core.voice.stt — Speech-to-Text module.

All tests mock the microphone and recognizer so they run in CI without
audio hardware.
"""

from __future__ import annotations

import os
import sys
import tempfile
import wave
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ensure project root is importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.voice.stt import STTProvider, STTResult, VoiceInput


# ---------------------------------------------------------------------------
# 1. STTProvider enum has all values
# ---------------------------------------------------------------------------

class TestSTTProvider:
    def test_enum_members(self):
        assert STTProvider.SYSTEM.value == "system"
        assert STTProvider.WHISPER_LOCAL.value == "whisper_local"
        assert STTProvider.GOOGLE_CLOUD.value == "google_cloud"
        assert STTProvider.OPENAI_WHISPER_API.value == "openai_whisper_api"

    def test_enum_count(self):
        assert len(STTProvider) == 4


# ---------------------------------------------------------------------------
# 2. STTResult dataclass fields
# ---------------------------------------------------------------------------

class TestSTTResult:
    def test_fields_present(self):
        r = STTResult(text="hello", confidence=0.9, provider="system",
                      duration_seconds=1.5, language="en")
        assert r.text == "hello"
        assert r.confidence == 0.9
        assert r.provider == "system"
        assert r.duration_seconds == 1.5
        assert r.language == "en"

    def test_defaults(self):
        r = STTResult(text="test")
        assert r.confidence == 0.0
        assert r.provider == ""
        assert r.duration_seconds == 0.0
        assert r.language == "en"


# ---------------------------------------------------------------------------
# 3. VoiceInput() creates without error
# ---------------------------------------------------------------------------

class TestVoiceInputInit:
    def test_creates_without_error(self):
        vi = VoiceInput()
        assert vi is not None

    def test_custom_provider(self):
        vi = VoiceInput(provider=STTProvider.WHISPER_LOCAL)
        assert vi._provider == STTProvider.WHISPER_LOCAL


# ---------------------------------------------------------------------------
# 4. is_available() returns bool
# ---------------------------------------------------------------------------

class TestIsAvailable:
    def test_returns_bool(self):
        vi = VoiceInput()
        result = vi.is_available()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# 5. transcribe with mock recognizer returns STTResult
# ---------------------------------------------------------------------------

class TestTranscribe:
    def test_transcribe_system_mock(self):
        mock_sr = MagicMock()
        mock_recognizer_instance = MagicMock()
        mock_recognizer_instance.recognize_google.return_value = "open my documents"
        mock_sr.Recognizer.return_value = mock_recognizer_instance

        vi = VoiceInput()
        vi._sr = mock_sr

        mock_audio = MagicMock()
        result = vi.transcribe(mock_audio, provider=STTProvider.SYSTEM)

        assert result is not None
        assert isinstance(result, STTResult)
        assert result.text == "open my documents"
        assert result.provider == "system"
        assert result.confidence > 0

    def test_transcribe_none_audio_returns_none(self):
        vi = VoiceInput()
        result = vi.transcribe(None)
        assert result is None


# ---------------------------------------------------------------------------
# 6. listen_and_transcribe with mock returns text
# ---------------------------------------------------------------------------

class TestListenAndTranscribe:
    def test_listen_and_transcribe_mock(self):
        vi = VoiceInput()

        mock_audio = MagicMock()
        vi.record = MagicMock(return_value=mock_audio)

        expected = STTResult(text="create a folder", confidence=0.85,
                             provider="system", duration_seconds=1.0)
        vi.transcribe = MagicMock(return_value=expected)

        result = vi.listen_and_transcribe(duration=5)

        assert result is not None
        assert result.text == "create a folder"
        vi.record.assert_called_once_with(duration_seconds=5)

    def test_listen_and_transcribe_no_audio(self):
        vi = VoiceInput()
        vi.record = MagicMock(return_value=None)

        result = vi.listen_and_transcribe()
        assert result is None


# ---------------------------------------------------------------------------
# 7. voice_prompt with mock returns string
# ---------------------------------------------------------------------------

class TestVoicePrompt:
    def test_voice_prompt_returns_text(self, capsys):
        vi = VoiceInput()
        vi.is_available = MagicMock(return_value=True)
        vi.listen_and_transcribe = MagicMock(
            return_value=STTResult(text="find large files", confidence=0.9,
                                   provider="system", duration_seconds=2.0)
        )

        result = vi.voice_prompt()

        assert result == "find large files"

    def test_voice_prompt_not_available(self, capsys):
        vi = VoiceInput()
        vi.is_available = MagicMock(return_value=False)

        result = vi.voice_prompt()

        assert result is None
        captured = capsys.readouterr()
        assert "not available" in captured.out


# ---------------------------------------------------------------------------
# 8. transcribe_file with mock .wav returns STTResult
# ---------------------------------------------------------------------------

class TestTranscribeFile:
    def test_transcribe_wav_file(self):
        # Create a minimal valid WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            with wave.open(f, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)  # 1 second of silence

        try:
            mock_sr = MagicMock()
            mock_recognizer = MagicMock()
            mock_recognizer.recognize_google.return_value = "hello world"
            mock_sr.Recognizer.return_value = mock_recognizer

            # Mock AudioFile context manager
            mock_audio_data = MagicMock()
            mock_recognizer.record.return_value = mock_audio_data
            mock_audio_file = MagicMock()
            mock_audio_file.__enter__ = MagicMock(return_value=mock_audio_file)
            mock_audio_file.__exit__ = MagicMock(return_value=False)
            mock_sr.AudioFile.return_value = mock_audio_file

            vi = VoiceInput()
            vi._sr = mock_sr

            result = vi.transcribe_file(tmp_path)

            assert result is not None
            assert isinstance(result, STTResult)
            assert result.text == "hello world"
        finally:
            os.unlink(tmp_path)

    def test_transcribe_file_not_found(self):
        vi = VoiceInput()
        result = vi.transcribe_file("/nonexistent/audio.wav")
        assert result is None


# ---------------------------------------------------------------------------
# 9. Error handling — no microphone returns graceful error
# ---------------------------------------------------------------------------

class TestNoMicrophone:
    def test_record_no_sr(self):
        vi = VoiceInput()
        vi._sr = None
        result = vi.record()
        assert result is None

    def test_record_microphone_oserror(self):
        mock_sr = MagicMock()
        mock_recognizer = MagicMock()
        mock_sr.Recognizer.return_value = mock_recognizer
        mock_sr.Microphone.side_effect = OSError("No microphone found")

        vi = VoiceInput()
        vi._sr = mock_sr

        result = vi.record()
        assert result is None

    def test_is_available_no_mic(self):
        mock_sr = MagicMock()
        mock_sr.Microphone.side_effect = OSError("No default input device")

        vi = VoiceInput()
        vi._sr = mock_sr

        assert vi.is_available() is False


# ---------------------------------------------------------------------------
# 10. Error handling — transcription fails returns None text
# ---------------------------------------------------------------------------

class TestTranscriptionFailure:
    def test_recognize_raises_returns_none(self):
        mock_sr = MagicMock()
        mock_recognizer = MagicMock()
        mock_recognizer.recognize_google.side_effect = Exception("Could not understand")
        mock_sr.Recognizer.return_value = mock_recognizer

        vi = VoiceInput()
        vi._sr = mock_sr

        mock_audio = MagicMock()
        result = vi.transcribe(mock_audio, provider=STTProvider.SYSTEM)
        assert result is None

    def test_unknown_provider_returns_none(self):
        vi = VoiceInput()
        mock_audio = MagicMock()
        # Pass a provider value that won't match any branch
        # by setting _provider to something and calling transcribe with None match
        result = vi.transcribe(mock_audio, provider=STTProvider.GOOGLE_CLOUD)
        # Without credentials set, this returns None
        assert result is None


# ---------------------------------------------------------------------------
# 11. is_available returns False when speech_recognition not installed
# ---------------------------------------------------------------------------

class TestSpeechRecognitionMissing:
    def test_is_available_false_when_sr_none(self):
        vi = VoiceInput()
        vi._sr = None
        assert vi.is_available() is False

    def test_transcribe_file_returns_none_when_sr_none(self):
        vi = VoiceInput()
        vi._sr = None
        result = vi.transcribe_file("/some/file.wav")
        assert result is None

    @patch.dict(sys.modules, {"speech_recognition": None})
    def test_import_fallback(self):
        """Verify _import_speech_recognition returns None on ImportError."""
        from core.voice.stt import _import_speech_recognition
        # With speech_recognition mocked as None in sys.modules, import fails
        result = _import_speech_recognition()
        assert result is None
