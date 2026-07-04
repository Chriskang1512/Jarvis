import inspect
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from jarvis.result_merge import UnifiedResult
from jarvis.voice import MockVoiceProvider, VoiceProvider, VoiceResult, VoiceService
from jarvis.voice import service as voice_service_module
from jarvis.voice.providers import base as voice_provider_base
from jarvis.voice.providers import mock as mock_provider_module
from jarvis.voice.providers import openai as openai_provider_module


class TestVoiceIntegration(unittest.TestCase):
    """Test v0.4 Beta.5 Voice Integration."""

    def test_voice_service_reads_unified_result_summary_only(self):
        """Check VoiceService sends only UnifiedResult.summary to provider."""
        provider = RecordingVoiceProvider()
        response = UnifiedResult(
            summary="오늘 일정은 15시 회의입니다.",
            results=(
                {
                    "capability": "calendar",
                    "result": "Meeting 15:00",
                },
            ),
            warnings=(
                {
                    "message": "Rain likely",
                },
            ),
            errors=(
                {
                    "message": "Calendar detail should not be spoken",
                },
            ),
            metadata={
                "execution_id": "exec_voice",
            },
        )

        result = VoiceService(provider=provider).speak(response)

        self.assertEqual(provider.seen_text, "오늘 일정은 15시 회의입니다.")
        self.assertEqual(result.text, "오늘 일정은 15시 회의입니다.")
        self.assertNotIn("Meeting 15:00", result.text)
        self.assertNotIn("Rain likely", result.text)
        self.assertNotIn("exec_voice", result.text)

    def test_mock_voice_provider_returns_same_text_without_audio(self):
        """Check MockVoiceProvider creates VoiceResult without real audio."""
        result = MockVoiceProvider().synthesize("오늘 일정은 15시 회의입니다.")

        self.assertIsInstance(result, VoiceResult)
        self.assertEqual(result.text, "오늘 일정은 15시 회의입니다.")
        self.assertIsNone(result.audio)
        self.assertEqual(result.provider, "mock")
        self.assertFalse(result.metadata["audio_generated"])
        self.assertFalse(result.metadata["playback_ready"])

    def test_voice_provider_can_be_replaced_by_dependency_injection(self):
        """Check VoiceService works the same with a different provider."""
        provider = DummyVoiceProvider()
        response = UnifiedResult(summary="테스트 응답")

        result = VoiceService(provider=provider).speak(response)

        self.assertEqual(result.text, "dummy: 테스트 응답")
        self.assertEqual(result.provider, "dummy")
        self.assertEqual(result.audio, b"audio")
        self.assertTrue(isinstance(provider, VoiceProvider))

    def test_voice_result_is_immutable(self):
        """Check VoiceResult is immutable after provider synthesis."""
        result = MockVoiceProvider().synthesize("hello")

        with self.assertRaises(FrozenInstanceError):
            result.text = "changed"

        with self.assertRaises(TypeError):
            result.metadata["audio_generated"] = True

    def test_voice_layer_does_not_import_forbidden_orchestration_layers(self):
        """Check Voice depends on UnifiedResult shape, not orchestration internals."""
        source = "\n".join(
            inspect.getsource(module)
            for module in [
                voice_service_module,
                voice_provider_base,
                mock_provider_module,
                openai_provider_module,
            ]
        )

        forbidden = [
            "jarvis.planner",
            "IntentPlanner",
            "jarvis.execution",
            "ExecutionGraph",
            "ExecutionGraphRunner",
            "jarvis.capabilities",
            "Capability",
        ]

        for value in forbidden:
            self.assertNotIn(value, source)

    def test_openai_voice_provider_placeholder_exists(self):
        """Check OpenAI voice provider file exists as a reserved provider hook."""
        self.assertTrue(hasattr(openai_provider_module, "OpenAIVoiceProvider"))

    def test_legacy_voice_providers_file_was_replaced_by_package(self):
        """Check provider package migration does not leave an ambiguous module file."""
        self.assertFalse((Path("jarvis") / "voice" / "providers.py").exists())


class RecordingVoiceProvider:
    """Provider stub that records text passed by VoiceService."""

    def __init__(self):
        """Create a recording provider."""
        self.seen_text = None

    def synthesize(self, text):
        """Record text and return it as a voice result."""
        self.seen_text = text
        return VoiceResult(
            text=text,
            audio=None,
            provider="recording",
            duration_ms=1,
            metadata={},
        )


class DummyVoiceProvider:
    """Provider stub used to prove DI."""

    def synthesize(self, text):
        """Return deterministic dummy audio."""
        return VoiceResult(
            text=f"dummy: {text}",
            audio=b"audio",
            provider="dummy",
            duration_ms=2,
            metadata={
                "audio_generated": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
