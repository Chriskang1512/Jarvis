from dataclasses import dataclass, field


@dataclass
class TTSConfig:
    """Store runtime configuration for text-to-speech providers."""

    provider: str = "pyttsx3"
    voice: str = "default"
    streaming: bool = True
    piper_path: str = "piper"
    model_path: str = ""


@dataclass
class ConversationConfig:
    """Store short-term conversation memory settings."""

    max_turns: int = 6
    max_tokens: int = 1200


@dataclass
class MemoryStoreConfig:
    """Store long-term memory backend settings."""

    path: str = "data/memory_store.json"


@dataclass
class JarvisConfig:
    """Store runtime configuration for Jarvis bootstrap."""

    provider: str = "mock"
    model: str = "mock"
    temperature: float = 0.7
    debug: bool = False
    profile: str = "jarvis"
    version: str = "v0.3.0-beta.6"
    tts: TTSConfig = field(default_factory=TTSConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    memory_store: MemoryStoreConfig = field(default_factory=MemoryStoreConfig)
