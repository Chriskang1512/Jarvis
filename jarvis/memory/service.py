class MemoryService:
    """Memory service that hides the concrete MemoryProvider."""

    def __init__(self, provider):
        """Create a memory service with one injected provider."""
        self.provider = provider

    def remember(self, key, value):
        """Remember one value using a key."""
        self.provider.remember(key, value)

    def recall(self, key):
        """Recall one value using a key."""
        return self.provider.recall(key)

    def clear(self):
        """Clear every remembered value."""
        self.provider.clear()
