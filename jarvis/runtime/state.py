"""Shared Runtime state contract for every present and future UI."""

from enum import Enum


class RuntimeState(str, Enum):
    IDLE = "Idle"
    LISTENING = "Listening"
    THINKING = "Thinking"
    PLANNING = "Planning"
    EXECUTING = "Executing"
    WAITING_PERMISSION = "WaitingPermission"
    VERIFYING = "Verifying"
    SPEAKING = "Speaking"
    COMPLETED = "Completed"
    FAILED = "Failed"
