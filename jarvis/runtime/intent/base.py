from typing import Protocol

from jarvis.runtime.intent.models import IntentContext, IntentParseResult


class IntentParser(Protocol):
    """Common contract for rule, AI, and hybrid intent parsers."""

    def parse(self, text: str, context: IntentContext) -> IntentParseResult:
        """Parse free text into structured intent data."""
        ...
