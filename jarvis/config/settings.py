from dataclasses import dataclass, field


@dataclass
class TTSConfig:
    """Store runtime configuration for text-to-speech providers."""

    provider: str = "console"
    voice: str = "default"
    streaming: bool = True
    piper_path: str = "piper"
    model_path: str = ""


@dataclass
class JarvisConfig:
    """Store runtime configuration for Jarvis bootstrap."""

    provider: str = "mock"
    model: str = "mock"
    temperature: float = 0.7
    debug: bool = False
    profile: str = "jarvis"
    version: str = "v0.3.0-beta.1"
    tts: TTSConfig = field(default_factory=TTSConfig)
