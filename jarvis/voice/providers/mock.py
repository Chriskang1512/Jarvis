from time import perf_counter

from jarvis.voice.models import VoiceResult


class MockVoiceProvider:
    """Mock voice provider that returns text without generating audio."""

    provider_name = "mock"

    def synthesize(self, text: str) -> VoiceResult:
        """Return the same text with no audio bytes."""
        started = perf_counter()
        return VoiceResult(
            text=text,
            audio=None,
            provider=self.provider_name,
            duration_ms=int((perf_counter() - started) * 1000),
            metadata={
                "audio_generated": False,
                "playback_ready": False,
            },
        )
