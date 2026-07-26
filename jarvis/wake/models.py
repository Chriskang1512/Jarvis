from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class WakeMethod(str, Enum):
    CLAP = "clap"
    VOICE = "voice"
    KEYBOARD = "keyboard"
    TOUCH_PORTAL = "touch_portal"
    MOBILE = "mobile"
    API = "api"
    BLE = "ble"


@dataclass(frozen=True)
class WakeEvent:
    method: WakeMethod
    provider_id: str
    event_id: str = ""
    occurred_at: str = ""
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.event_id:
            object.__setattr__(self, "event_id", f"WK-{uuid4().hex[:10].upper()}")
        if not self.occurred_at:
            object.__setattr__(
                self,
                "occurred_at",
                datetime.now().isoformat(timespec="milliseconds"),
            )
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class WakeProfile:
    name: str = "default"
    priority: tuple[WakeMethod, ...] = (
        WakeMethod.CLAP,
        WakeMethod.VOICE,
        WakeMethod.KEYBOARD,
        WakeMethod.TOUCH_PORTAL,
        WakeMethod.MOBILE,
        WakeMethod.API,
    )
    enabled: tuple[WakeMethod, ...] = (
        WakeMethod.CLAP,
        WakeMethod.VOICE,
        WakeMethod.KEYBOARD,
        WakeMethod.TOUCH_PORTAL,
    )

    def __post_init__(self):
        object.__setattr__(self, "priority", tuple(self.priority))
        object.__setattr__(self, "enabled", tuple(self.enabled))


@dataclass(frozen=True)
class WakeSettings:
    profile: WakeProfile = field(default_factory=WakeProfile)
    voice_phrases: tuple[str, ...] = ("hey jarvis", "헤이 자비스", "자비스")
    keyboard_hotkey: str = "ctrl+space"
    polling_interval_seconds: float = 0.02

    def __post_init__(self):
        object.__setattr__(
            self,
            "voice_phrases",
            tuple(normalize_phrase(item) for item in self.voice_phrases if normalize_phrase(item)),
        )


def normalize_phrase(value):
    return " ".join(str(value or "").strip().lower().split())
