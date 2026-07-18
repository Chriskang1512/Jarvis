from dataclasses import dataclass, field


@dataclass
class TTSConfig:
    """Store runtime configuration for text-to-speech providers."""

    provider: str = "pyttsx3"
    voice_profile: str = "jarvis_default"
    voice: str = "default"
    speed: float = 1.0
    pitch: int = 0
    volume: float = 1.0
    language: str = "ko"
    openai_model: str = "gpt-4o-mini-tts"
    response_format: str = "wav"
    streaming: bool = True
    piper_path: str = "piper"
    model_path: str = ""


@dataclass
class STTConfig:
    """Store runtime configuration for speech-to-text providers."""

    provider: str = "openai"
    language: str = "ko-KR"
    device: str = "default"
    openai_model: str = "gpt-4o-transcribe"
    openai_language: str = "ko"
    min_record_seconds: float = 4.0
    max_record_seconds: float = 20.0
    silence_timeout: float = 3.0


@dataclass
class ConversationConfig:
    """Store short-term conversation memory settings."""

    max_turns: int = 6
    max_tokens: int = 1200
    follow_up_timeout: float = 8.0


@dataclass
class MemoryStoreConfig:
    """Store long-term memory backend settings."""

    path: str = "data/memory_store.json"


@dataclass
class WeatherConfig:
    """Store Weather Ability provider settings."""

    provider: str = "mock"
    fallback_to_mock: bool = True
    openweather_lang: str = "kr"
    default_location: str = "강릉"


@dataclass
class CalendarConfig:
    """Store Calendar Ability provider settings."""

    provider: str = "mock"
    allow_mock_fallback: bool = True
    timezone: str = "Asia/Seoul"
    google_credentials_path: str = "data/credentials/google_token.json"
    google_client_secret_path: str = "client_secret.json"


@dataclass
class AIIntentConfig:
    """Store AI Intent Parser settings."""

    enabled: bool = False
    provider: str = "openai"
    model: str = ""
    timeout: float = 8.0
    min_confidence: float = 0.70
    max_output_tokens: int = 300
    reasoning_effort: str = "low"
    verbosity: str = "low"


@dataclass
class JarvisConfig:
    """Store runtime configuration for Jarvis bootstrap."""

    provider: str = "mock"
    chat_provider: str = "mock"
    model: str = "mock"
    temperature: float = 0.7
    debug: bool = False
    profile: str = "jarvis"
    version: str = "v0.4.0"
    tts: TTSConfig = field(default_factory=TTSConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    memory_store: MemoryStoreConfig = field(default_factory=MemoryStoreConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    ai_intent: AIIntentConfig = field(default_factory=AIIntentConfig)
