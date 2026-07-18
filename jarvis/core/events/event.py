"""Core event contract for Jarvis runtime."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import uuid


EVENT_VERSION = 1


@dataclass(frozen=True)
class BaseEvent:
    """Durable event envelope shared by Core, Abilities, and future providers."""

    event_type: str
    aggregate_type: str
    aggregate_id: str
    revision: int = 0
    payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    event_id: str = ""
    idempotency_key: str = ""
    trace_id: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    occurred_at: str = ""
    source: str = "jarvis"
    version: int = EVENT_VERSION

    def __post_init__(self):
        """Fill stable defaults."""
        if self.event_id == "":
            object.__setattr__(self, "event_id", new_event_id())

        if self.occurred_at == "":
            object.__setattr__(self, "occurred_at", datetime.now().isoformat(timespec="seconds"))

    def to_dict(self):
        """Return a JSON-safe event dictionary."""
        return asdict(self)

    def to_json(self):
        """Serialize the event for replay/debug recording."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data):
        """Load an event from a dictionary."""
        return cls(**dict(data or {}))

    @classmethod
    def from_json(cls, text):
        """Load an event from a JSON string."""
        return cls.from_dict(json.loads(text))


def new_event_id():
    """Return a compact Core event ID."""
    return f"EV-{uuid.uuid4().hex[:12].upper()}"
