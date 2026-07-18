"""Core EventBus exceptions."""


class EventBusError(Exception):
    """Base class for event bus failures."""


class EventHandlerError(EventBusError):
    """Raised by handlers that want to expose a structured failure."""


class TemporaryEventHandlerError(EventHandlerError):
    """Retryable temporary handler failure."""


class EventHandlerTimeout(EventHandlerError):
    """Handler exceeded its configured timeout."""
