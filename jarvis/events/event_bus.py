from collections import defaultdict

from jarvis.events.types import JarvisEvent


class EventBus:
    """Generic in-memory EventBus for Jarvis modules."""

    def __init__(self):
        """Create empty subscriber lists for named and global events."""
        self.subscribers = defaultdict(list)
        self.global_subscribers = []

    def subscribe(self, event_type, handler):
        """Subscribe a handler to one event type."""
        self.subscribers[event_type].append(handler)

    def subscribe_all(self, handler):
        """Subscribe a handler to every event published by Jarvis."""
        self.global_subscribers.append(handler)

    def publish(self, event):
        """Publish one event to matching and global subscribers."""
        handlers = self.subscribers[event.event_type]

        for handler in handlers:
            handler(event)

        for handler in self.global_subscribers:
            handler(event)

    def publish_state(self, event_type, state):
        """Create an event from an event type and JarvisState, then publish it."""
        event = JarvisEvent(event_type=event_type, state=state)
        self.publish(event)

    def publish_async(self, event):
        """Reserve a future async publish API without changing callers later."""
        # TODO: Replace this stub with asyncio-based fan-out when Jarvis needs it.
        self.publish(event)
