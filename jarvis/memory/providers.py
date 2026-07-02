from typing import Protocol


class MemoryProvider(Protocol):
    """Interface for future memory providers such as SQLite or Vector DB."""

    def remember(self, key, value):
        """Store one memory value by key."""
        ...

    def recall(self, key):
        """Return one remembered value by key."""
        ...

    def clear(self):
        """Remove every remembered value."""
        ...


class MockMemoryProvider:
    """Simple in-memory provider used before persistent memory is connected."""

    def __init__(self):
        """Create an empty mock memory store."""
        self.memories = {}

    def remember(self, key, value):
        """Store one memory value in memory."""
        self.memories[key] = value

    def recall(self, key):
        """Return one memory value or an empty string."""
        return self.memories.get(key, "")

    def clear(self):
        """Remove all mock memories."""
        self.memories.clear()
