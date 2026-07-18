"""Voice pipeline package for Jarvis."""

from jarvis.voice.conversation import (
    CONVERSATION_CLOSED,
    CONVERSATION_FOLLOW_UP,
    CONVERSATION_IDLE,
    CONVERSATION_LISTENING,
    CONVERSATION_SPEAKING,
    CONVERSATION_THINKING,
    ConversationSession,
    create_conversation_session,
)
from jarvis.voice.models import VoiceResult
from jarvis.voice.pipeline import VoicePipeline
from jarvis.voice.profiles import VoiceProfile, VoiceRegistry
from jarvis.voice.provider import VoiceProvider
from jarvis.voice.providers import create_stt_provider, create_tts_provider
from jarvis.voice.providers import ConsoleSpeechToTextProvider, MicrophoneSpeechToTextProvider
from jarvis.voice.providers import HybridSpeechToTextProvider
from jarvis.voice.providers import OpenAISpeechToTextProvider, OpenAITextToSpeechProvider
from jarvis.voice.providers.mock import MockVoiceProvider
from jarvis.voice.service import VoiceService
from jarvis.voice.session import VoiceSession, create_voice_session
from jarvis.voice.text_normalizer import normalize_tts_text
from jarvis.voice.wake_word import WakeWordListener

__all__ = [
    "ConsoleSpeechToTextProvider",
    "CONVERSATION_CLOSED",
    "CONVERSATION_FOLLOW_UP",
    "CONVERSATION_IDLE",
    "CONVERSATION_LISTENING",
    "CONVERSATION_SPEAKING",
    "CONVERSATION_THINKING",
    "ConversationSession",
    "HybridSpeechToTextProvider",
    "MicrophoneSpeechToTextProvider",
    "MockVoiceProvider",
    "OpenAISpeechToTextProvider",
    "OpenAITextToSpeechProvider",
    "VoiceProfile",
    "VoiceRegistry",
    "VoicePipeline",
    "VoiceProvider",
    "VoiceResult",
    "VoiceService",
    "VoiceSession",
    "WakeWordListener",
    "create_stt_provider",
    "create_tts_provider",
    "create_conversation_session",
    "create_voice_session",
    "normalize_tts_text",
]
