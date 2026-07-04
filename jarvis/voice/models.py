from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class VoiceResult:
    """Result produced by the Voice layer before audio playback exists."""

    text: str
    audio: bytes | None
    provider: str
    duration_ms: int
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        """Freeze nested metadata after construction."""
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))

    def to_dict(self):
        """Return a stable dictionary contract."""
        return {
            "text": self.text,
            "audio": self.audio,
            "provider": self.provider,
            "duration_ms": self.duration_ms,
            "metadata": thaw_mapping(self.metadata),
        }


def freeze_mapping(value):
    """Recursively freeze metadata dictionaries."""
    if isinstance(value, dict):
        return MappingProxyType(
            {
                key: freeze_mapping(item)
                for key, item in value.items()
            }
        )

    if isinstance(value, (list, tuple)):
        return tuple(freeze_mapping(item) for item in value)

    return value


def thaw_mapping(value):
    """Recursively convert frozen metadata to plain containers."""
    if isinstance(value, MappingProxyType):
        return {
            key: thaw_mapping(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [thaw_mapping(item) for item in value]

    return value
