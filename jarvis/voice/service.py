from time import perf_counter

from jarvis.voice.models import VoiceResult
from jarvis.voice.providers.mock import MockVoiceProvider


class VoiceService:
    """Convert a UnifiedResult summary into a provider-specific VoiceResult."""

    def __init__(self, provider=None):
        """Create a voice service with an injectable provider."""
        self.provider = provider or MockVoiceProvider()

    def speak(self, response) -> VoiceResult:
        """Speak only the unified response summary through the provider."""
        started = perf_counter()
        voice_result = self.provider.synthesize(response.summary)
        elapsed_ms = int((perf_counter() - started) * 1000)

        if voice_result.duration_ms > 0:
            return voice_result

        return VoiceResult(
            text=voice_result.text,
            audio=voice_result.audio,
            provider=voice_result.provider,
            duration_ms=elapsed_ms,
            metadata=voice_result.metadata,
        )
