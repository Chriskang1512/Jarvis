from enum import Enum


class NodeStatus(str, Enum):
    """Execution node lifecycle states."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


def result_status(status):
    """Return the external result status value."""
    return status.value.lower()
