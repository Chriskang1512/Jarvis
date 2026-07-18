from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TranscriptResult:
    """Normalized result contract for STT providers."""

    success: bool
    text: str = ""
    raw_text: str = ""
    normalized_text: str = ""
    provider: str = ""
    model: str = ""
    language: str = ""
    latency_ms: int = 0
    fallback_used: bool = False
    correction_applied: bool = False
    error_code: str = ""
    error_message: str = ""
    metadata: dict = field(default_factory=dict)
    alternatives: tuple = ()
    confidence: Optional[float] = None
    audio_duration_ms: Optional[int] = None

    def display_text(self):
        """Return the best human-readable transcript."""
        return self.normalized_text or self.text or self.raw_text
