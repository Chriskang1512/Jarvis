"""Google provider metadata models."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class GoogleProviderMetadata:
    """Common metadata reported by Google provider operations."""

    provider: str = "google"
    service: str = ""
    action: str = ""
    scopes: tuple[str, ...] = field(default_factory=tuple)
    trace_id: str = ""
    correlation_id: str = ""
    execution_time_ms: int = 0
    timestamp: str = ""

    def __post_init__(self):
        """Fill derived defaults."""
        if self.timestamp == "":
            object.__setattr__(self, "timestamp", datetime.now().isoformat(timespec="seconds"))

    def to_dict(self):
        """Return a serializable metadata dictionary."""
        return {
            "provider": self.provider,
            "service": self.service,
            "action": self.action,
            "scopes": list(self.scopes),
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp,
        }
