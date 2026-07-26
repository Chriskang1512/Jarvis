"""Wake Manager and provider contracts."""

from jarvis.wake.clap import ClapDetector, ClapDetectorSettings, SoundDeviceClapMonitor
from jarvis.wake.manager import WakeManager
from jarvis.wake.models import WakeEvent, WakeMethod, WakeProfile, WakeSettings
from jarvis.wake.providers import (
    ApiWakeProvider,
    ClapWakeProvider,
    KeyboardWakeProvider,
    MobileWakeProvider,
    TouchPortalWakeProvider,
    WakeWordProvider,
)

__all__ = [
    "ApiWakeProvider",
    "ClapDetector",
    "ClapDetectorSettings",
    "ClapWakeProvider",
    "SoundDeviceClapMonitor",
    "KeyboardWakeProvider",
    "MobileWakeProvider",
    "TouchPortalWakeProvider",
    "WakeEvent",
    "WakeManager",
    "WakeMethod",
    "WakeProfile",
    "WakeSettings",
    "WakeWordProvider",
]
