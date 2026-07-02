from dataclasses import dataclass


@dataclass
class JarvisConfig:
    """Store runtime configuration for Jarvis bootstrap."""

    provider: str = "mock"
    model: str = "mock"
    temperature: float = 0.7
    debug: bool = False
    profile: str = "jarvis"
    version: str = "v0.2.0-alpha.4"
