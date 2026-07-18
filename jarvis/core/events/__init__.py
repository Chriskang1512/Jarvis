"""Core EventBus foundation."""

from jarvis.core.events.context import EventContext
from jarvis.core.events.event import BaseEvent
from jarvis.core.events.event_bus import InMemoryEventBus, PublishResult, RetryPolicy
from jarvis.core.events.handlers import (
    EntityGraphContactHandler,
    EventHistoryHandler,
    EventMetricsHandler,
    ReminderScheduleHandler,
)
from jarvis.core.events.recorder import DeadLetterRecorder, EventRecorder, ReplayOptions, ReplayResult, replay_events
from jarvis.core.events.registry import create_event_bus

__all__ = [
    "BaseEvent",
    "DeadLetterRecorder",
    "EntityGraphContactHandler",
    "EventContext",
    "EventHistoryHandler",
    "EventMetricsHandler",
    "EventRecorder",
    "InMemoryEventBus",
    "PublishResult",
    "ReplayOptions",
    "ReplayResult",
    "ReminderScheduleHandler",
    "RetryPolicy",
    "create_event_bus",
    "replay_events",
]
