from typing import Protocol


class LLMProvider(Protocol):
    """Common contract for every Jarvis LLM provider."""

    def generate(self, prompt, **options):
        """Generate one complete response."""
        ...

    def generate_stream(self, prompt):
        """Generate response chunks when supported."""
        ...

    def metadata(self):
        """Return provider capability metadata."""
        ...
