"""Event context helpers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EventContext:
    """Optional context passed alongside event publication."""

    trace_id: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    idempotency_key: str = ""
    source: str = "jarvis"
    user_id: str = ""
    session_id: str = ""
    conversation_id: str = ""
    task_id: str = ""
    planner_id: str = ""
    permission_scope: str = ""
    runtime: str = ""

    def to_metadata(self):
        """Return non-empty context values as event metadata."""
        return {
            key: value
            for key, value in {
                "user_id": self.user_id,
                "session_id": self.session_id,
                "conversation_id": self.conversation_id,
                "task_id": self.task_id,
                "planner_id": self.planner_id,
                "permission_scope": self.permission_scope,
                "runtime": self.runtime,
            }.items()
            if value
        }
