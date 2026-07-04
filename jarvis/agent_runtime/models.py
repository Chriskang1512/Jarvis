from dataclasses import dataclass, field
from enum import Enum


class AgentRuntimeState(Enum):
    """Lifecycle states for the minimal Agent Runtime."""

    STOPPED = "STOPPED"
    IDLE = "IDLE"
    CHECKING = "CHECKING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AgentTickResult:
    """Result from one manual AgentRuntime tick."""

    runtime_state: AgentRuntimeState
    checked_at: object
    due_count: int
    trigger_results: tuple = field(default_factory=tuple)
    error: str = ""

    def to_dict(self):
        """Return a stable dictionary contract."""
        return {
            "runtime_state": self.runtime_state.value,
            "checked_at": self.checked_at.isoformat() if hasattr(self.checked_at, "isoformat") else self.checked_at,
            "due_count": self.due_count,
            "trigger_results": [
                result.to_dict() if hasattr(result, "to_dict") else result
                for result in self.trigger_results
            ],
            "error": self.error,
        }
