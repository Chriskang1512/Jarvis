import io
import unittest
from contextlib import redirect_stdout

from jarvis.config.loader import create_config_from_dict
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.voice.providers import (
    ConsoleTextToSpeechProvider,
    PiperTextToSpeechProvider,
    Pyttsx3TextToSpeechProvider,
    create_tts_provider,
)


class TestTTSProviders(unittest.TestCase):
    """Test that TTS providers keep the shared speech contract."""

    def test_default_config_selects_pyttsx3_provider(self):
        """Check that pyttsx3 is the default local TTS provider."""
        config = create_config_from_dict({})

        provider = create_tts_provider(config.tts)

        self.assertIsInstance(provider, Pyttsx3TextToSpeechProvider)

    def test_config_selects_piper_provider(self):
        """Check that config can select the Piper TTS provider."""
        config = create_config_from_dict(
            {
                "tts": {
                    "provider": "piper",
                    "voice": "default",
                    "streaming": True,
                    "piper_path": "piper",
                    "model_path": "missing.onnx",
                }
            }
        )
        diagnostics = DiagnosticsCollector()

        provider = create_tts_provider(config.tts, diagnostics_collector=diagnostics)

        self.assertIsInstance(provider, PiperTextToSpeechProvider)
        self.assertEqual(provider.voice, "default")
        self.assertTrue(provider.streaming_enabled)
        self.assert_event_logged(diagnostics, "voice.provider.selected")

    def test_console_provider_speak_stream_contract(self):
        """Check console TTS streaming chunks and diagnostics events."""
        diagnostics = DiagnosticsCollector()
        provider = ConsoleTextToSpeechProvider(diagnostics_collector=diagnostics)

        output = io.StringIO()
        with redirect_stdout(output):
            provider.speak_stream(["hello", "world"])

        self.assertIn("hello", output.getvalue())
        self.assertIn("world", output.getvalue())
        self.assert_event_logged(diagnostics, "voice.tts.started")
        self.assert_event_logged(diagnostics, "voice.tts.chunk.generated")
        self.assert_event_logged(diagnostics, "voice.tts.playback.started")
        self.assert_event_logged(diagnostics, "voice.tts.playback.completed")

    def test_piper_provider_falls_back_when_not_configured(self):
        """Check that Piper keeps the contract even without local binaries."""
        diagnostics = DiagnosticsCollector()
        provider = PiperTextToSpeechProvider(
            piper_path="missing-piper-executable",
            model_path="missing.onnx",
            diagnostics_collector=diagnostics,
        )

        output = io.StringIO()
        with redirect_stdout(output):
            provider.speak("hello")

        self.assertIn("Falling back to console output", output.getvalue())
        self.assert_event_logged(diagnostics, "voice.tts.error")

    def test_factory_keeps_existing_provider_names(self):
        """Check existing console and pyttsx3 provider names still resolve."""
        self.assertIsInstance(create_tts_provider("console"), ConsoleTextToSpeechProvider)
        self.assertIsInstance(create_tts_provider("pyttsx3"), Pyttsx3TextToSpeechProvider)

    def assert_event_logged(self, diagnostics, expected_message):
        """Check that one diagnostics event was logged."""
        messages = [event.message for event in diagnostics.get_snapshot().events]
        self.assertIn(expected_message, messages)


if __name__ == "__main__":
    unittest.main()
