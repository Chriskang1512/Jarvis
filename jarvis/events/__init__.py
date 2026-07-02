"""Generic event system for Jarvis Core and future UI layers."""

from jarvis.events.adapters import ConsoleEventAdapter, RiveVisualAdapter
from jarvis.events.event_bus import EventBus
from jarvis.events.types import (
    JarvisEmotion,
    JarvisEvent,
    JarvisEventName,
    JarvisEventType,
    JarvisState,
    JarvisStatus,
)
