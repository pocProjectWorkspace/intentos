"""IntentOS Voice — speech-to-text input and text-to-speech output."""

from core.voice.stt import STTProvider, STTResult, VoiceInput
from core.voice.tts import TTSProvider, TTSResult, VoiceOutput

__all__ = [
    "STTProvider", "STTResult", "VoiceInput",
    "TTSProvider", "TTSResult", "VoiceOutput",
]
