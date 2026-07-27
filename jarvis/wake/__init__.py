"""Wake Manager and provider contracts."""

from jarvis.wake.clap import ClapDetector, ClapDetectorSettings, SoundDeviceClapMonitor
from jarvis.wake.calibration import (
    AudioFeature,
    WakeCalibrationProfile,
    derive_wake_calibration,
    load_wake_calibration,
    save_wake_calibration,
)
from jarvis.wake.manager import WakeManager
from jarvis.wake.models import WakeEvent, WakeMethod, WakeProfile, WakeSettings
from jarvis.wake.providers import (
    ApiWakeProvider,
    ClapWakeProvider,
    KeyboardWakeProvider,
    MicrophoneWakeWordProvider,
    MobileWakeProvider,
    TouchPortalWakeProvider,
    WakeWordProvider,
)

__all__ = [
    "ApiWakeProvider",
    "AudioFeature",
    "ClapDetector",
    "ClapDetectorSettings",
    "ClapWakeProvider",
    "SoundDeviceClapMonitor",
    "KeyboardWakeProvider",
    "MicrophoneWakeWordProvider",
    "MobileWakeProvider",
    "TouchPortalWakeProvider",
    "WakeEvent",
    "WakeCalibrationProfile",
    "WakeManager",
    "WakeMethod",
    "WakeProfile",
    "WakeSettings",
    "WakeWordProvider",
    "derive_wake_calibration",
    "load_wake_calibration",
    "save_wake_calibration",
]
