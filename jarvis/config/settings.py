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
class WakeConfig:
    """Store enabled wake methods and user ordering."""

    enabled: bool = True
    profile: str = "default"
    primary: str = "clap"
    methods: tuple[str, ...] = ("clap", "voice", "keyboard", "touch_portal")
    voice_phrases: tuple[str, ...] = ("hey jarvis", "헤이 자비스", "자비스")
    keyboard_hotkey: str = "ctrl+space"
    clap_peak_threshold: float = 0.55
    clap_rms_threshold: float = 0.08
    clap_crest_factor_threshold: float = 3.0
    clap_min_gap_seconds: float = 0.12
    clap_max_gap_seconds: float = 0.8
    clap_settle_seconds: float = 0.5
    clap_second_threshold_ratio: float = 0.65
    clap_release_threshold_ratio: float = 0.35
    clap_noise_floor_multiplier: float = 4.0


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
    provider: str = "sqlite"
    sqlite_path: str = "data/jarvis_memory.db"


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
class ContactsConfig:
    """Store Contacts Ability provider settings."""

    provider: str = "memory"
    google_credentials_path: str = "data/credentials/google_token.json"
    google_client_secret_path: str = "client_secret.json"


@dataclass
class MailConfig:
    """Store Mail Ability provider settings."""

    provider: str = "mock"
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
    wake: WakeConfig = field(default_factory=WakeConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    memory_store: MemoryStoreConfig = field(default_factory=MemoryStoreConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    contacts: ContactsConfig = field(default_factory=ContactsConfig)
    mail: MailConfig = field(default_factory=MailConfig)
    ai_intent: AIIntentConfig = field(default_factory=AIIntentConfig)
