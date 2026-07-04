from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Clock interface for deterministic scheduler tests."""

    def now(self) -> datetime:
        """Return the current time."""
        ...


class SystemClock:
    """System clock implementation."""

    def now(self):
        """Return current local datetime."""
        return datetime.now()


class FixedClock:
    """Deterministic clock for tests."""

    def __init__(self, fixed_now):
        """Create a fixed clock."""
        self.fixed_now = fixed_now

    def now(self):
        """Return the configured fixed datetime."""
        return self.fixed_now
