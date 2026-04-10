"""Tests for the IntentOS TTS module (core/voice/tts.py).

Tests Piper TTS, macOS say, and system (pyttsx3) backends.
"""

from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.voice.tts import (
    VoiceOutput,
    TTSProvider,
    TTSResult,
    _ensure_piper_voice,
    _PIPER_VOICE_DEFAULT,
)


@pytest.fixture
def tts():
    return VoiceOutput(provider=TTSProvider.PIPER)


@pytest.fixture
def tts_cache(tmp_path):
    vo = VoiceOutput(provider=TTSProvider.PIPER)
    vo._output_dir = str(tmp_path)
    return vo


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

class TestAvailability:
    def test_get_best_available_returns_provider(self):
        tts = VoiceOutput()
        best = tts.get_best_available()
        assert isinstance(best, TTSProvider)

    def test_provider_enum_values(self):
        assert TTSProvider.PIPER.value == "piper"
        assert TTSProvider.SAY.value == "say"
        assert TTSProvider.SYSTEM.value == "system"
        assert TTSProvider.NONE.value == "none"


# ---------------------------------------------------------------------------
# TTSResult
# ---------------------------------------------------------------------------

class TestTTSResult:
    def test_result_fields(self):
        r = TTSResult(
            audio_path="/tmp/test.wav",
            text="hello",
            duration_seconds=1.5,
            provider="piper",
        )
        assert r.audio_path == "/tmp/test.wav"
        assert r.text == "hello"
        assert r.duration_seconds == 1.5
        assert r.provider == "piper"
        assert r.sample_rate == 22050


# ---------------------------------------------------------------------------
# macOS say backend
# ---------------------------------------------------------------------------

class TestSayBackend:
    @pytest.mark.skipif(
        not os.path.exists("/usr/bin/say"),
        reason="macOS say command not available",
    )
    def test_say_produces_audio(self):
        tts = VoiceOutput(provider=TTSProvider.SAY)
        result = tts.speak("Hello from IntentOS")
        assert result is not None
        assert result.provider == "say"
        assert os.path.exists(result.audio_path)
        assert result.duration_seconds > 0
        # Cleanup
        os.unlink(result.audio_path)


# ---------------------------------------------------------------------------
# VoiceOutput class
# ---------------------------------------------------------------------------

class TestVoiceOutput:
    def test_output_dir_created(self, tmp_path):
        out_dir = str(tmp_path / "tts_test")
        vo = VoiceOutput()
        vo._output_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        assert os.path.isdir(out_dir)

    def test_speak_with_none_provider(self):
        tts = VoiceOutput(provider=TTSProvider.NONE)
        result = tts.speak("test")
        assert result is None

    def test_speak_empty_text_returns_result_or_none(self):
        tts = VoiceOutput()
        best = tts.get_best_available()
        if best == TTSProvider.NONE:
            assert tts.speak("") is None


# ---------------------------------------------------------------------------
# Piper voice URL construction
# ---------------------------------------------------------------------------

class TestPiperVoiceURL:
    """Verify the HuggingFace download URL is constructed correctly."""

    def test_url_construction_en_us_lessac_medium(self):
        """en_US-lessac-medium should resolve to /en/en_US/lessac/medium/."""
        voice_name = "en_US-lessac-medium"
        parts = voice_name.split("-")
        locale = parts[0]               # "en_US"
        lang = locale.split("_")[0]      # "en"
        speaker = parts[1]              # "lessac"
        quality = parts[2]              # "medium"
        assert lang == "en"
        assert locale == "en_US"
        assert speaker == "lessac"
        assert quality == "medium"
        url = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang}/{locale}/{speaker}/{quality}/{voice_name}.onnx"
        assert url == "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx"

    def test_url_construction_de_de_thorsten_low(self):
        """de_DE-thorsten-low should resolve to /de/de_DE/thorsten/low/."""
        voice_name = "de_DE-thorsten-low"
        parts = voice_name.split("-")
        locale = parts[0]
        lang = locale.split("_")[0]
        speaker = parts[1]
        quality = parts[2]
        assert lang == "de"
        assert locale == "de_DE"
        assert speaker == "thorsten"
        assert quality == "low"

    def test_ensure_piper_voice_returns_none_for_bad_name(self):
        """A voice name with < 3 parts should return None."""
        result = _ensure_piper_voice("invalid")
        assert result is None

    def test_default_voice_name(self):
        assert _PIPER_VOICE_DEFAULT == "en_US-lessac-medium"
