from typing import Protocol, runtime_checkable

from jarvis.voice.models import VoiceResult


@runtime_checkable
class VoiceProvider(Protocol):
    """Provider interface for text-to-audio synthesis."""

    def synthesize(self, text: str) -> VoiceResult:
        """Synthesize one text response into a voice result."""
        ...
