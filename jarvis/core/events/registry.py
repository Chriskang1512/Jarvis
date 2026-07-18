"""EventBus registry helpers."""

from jarvis.core.events.event_bus import InMemoryEventBus
from jarvis.core.events.handlers import EventHistoryHandler, EventMetricsHandler


def create_event_bus(recorder=None, include_defaults=True):
    """Create an in-memory EventBus with optional default observers."""
    bus = InMemoryEventBus(recorder=recorder)

    if include_defaults:
        bus.subscribe("*", EventHistoryHandler())
        bus.subscribe("*", EventMetricsHandler())

    return bus
