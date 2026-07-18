import io
import unittest
from contextlib import redirect_stdout

from jarvis.brain import IntentRuntime, RuntimeContext
from jarvis.diagnostics.runtime_console import RuntimeDevConsole
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolDispatcher, ToolMetadata, ToolResult, create_default_tool_registry
from jarvis.tools.registry import ToolRegistry
from jarvis.voice import create_voice_session, normalize_tts_text
from jarvis.voice.pipeline import VoicePipeline


class TestRuntimeDevConsole(unittest.TestCase):
    """Test v0.5.0 Beta.2.5 runtime console rendering."""

    def test_render_successful_runtime_result(self):
        """Check renderer includes core RuntimeResult fields."""
        dispatcher = ToolDispatcher(registry=create_default_tool_registry())
        runtime = IntentRuntime(tool_dispatcher=dispatcher)

        result = runtime.run(
            RuntimeContext(
                text="what time is it",
                source="voice",
                session_id="37D5AB36",
            )
        )

        output = RuntimeDevConsole().render(result, theme="simple", provider="openai")

        self.assertIn("Input", output)
        self.assertIn("Jarvis Runtime", output)
        self.assertIn("v0.5.0 Beta.5.3", output)
        self.assertIn("Provider", output)
        self.assertIn("OpenAI", output)
        self.assertIn("what time is it", output)
        self.assertIn("Intent", output)
        self.assertIn("time.lookup", output)
        self.assertIn("confidence:", output)
        self.assertIn("Permission", output)
        self.assertIn("safe / allowed", output)
        self.assertIn("Tool", output)
        self.assertIn("time", output)
        self.assertIn("resolved: true", output)
        self.assertIn("Response", output)
        self.assertIn("Elapsed", output)
        self.assertIn("ms", output)
        self.assertIn("Runtime ID", output)
        self.assertIn(result.diagnostics.runtime_id, output)
        self.assertIn("Session", output)
        self.assertIn("37D5AB36", output)

    def test_render_rejects_unknown_theme(self):
        """Check future themes are explicit instead of silently ignored."""
        with self.assertRaises(ValueError):
            RuntimeDevConsole().render(theme="rich")

    def test_render_fallback_runtime_result(self):
        """Check renderer explains fallback when Runtime did not handle input."""
        dispatcher = ToolDispatcher(registry=create_default_tool_registry())
        runtime = IntentRuntime(tool_dispatcher=dispatcher)

        result = runtime.run("tell me a story", input_source="voice")

        output = RuntimeDevConsole().render(
            result,
            fallback="mock_llm",
            response="hello",
        )

        self.assertIn("Intent", output)
        self.assertIn("unmatched", output)
        self.assertIn("Fallback", output)
        self.assertIn("mock_llm", output)
        self.assertIn("hello", output)
        self.assertIn("resolved: false", output)

    def test_voice_pipeline_prints_runtime_console_when_enabled(self):
        """Check VoicePipeline prints renderer output only when one is provided."""
        registry = ToolRegistry()
        registry.register(EchoTool())
        dispatcher = ToolDispatcher(registry=registry)
        runtime = IntentRuntime(tool_dispatcher=dispatcher)
        pipeline = VoicePipeline(
            wake_listener=ImmediateWakeListener(),
            stt_provider=FixedSTTProvider("echo hello"),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            voice_session=create_voice_session(),
            intent_runtime=runtime,
            runtime_console=RuntimeDevConsole(),
        )

        output = io.StringIO()
        with redirect_stdout(output):
            pipeline.run_once()

        self.assertIn("Input", output.getvalue())
        self.assertIn("echo hello", output.getvalue())
        self.assertIn("test.echo", output.getvalue())
        self.assertIn("Session", output.getvalue())

    def test_voice_pipeline_runtime_console_prints_provider(self):
        """Check VoicePipeline passes the active provider to the console."""
        pipeline = VoicePipeline(
            wake_listener=ImmediateWakeListener(),
            stt_provider=FixedSTTProvider("tell me something"),
            chat_service=CapturingChatService(provider=NamedProvider("openai")),
            tts_provider=CapturingTTSProvider(),
            voice_session=create_voice_session(),
            intent_runtime=IntentRuntime(tool_dispatcher=ToolDispatcher(registry=ToolRegistry())),
            runtime_console=RuntimeDevConsole(),
        )

        output = io.StringIO()
        with redirect_stdout(output):
            pipeline.run_once()

        self.assertIn("Provider", output.getvalue())
        self.assertIn("OpenAI", output.getvalue())

    def test_voice_pipeline_prints_tts_debug_blocks(self):
        """Check VoicePipeline prints response and TTS input length."""
        pipeline = VoicePipeline(
            wake_listener=ImmediateWakeListener(),
            stt_provider=FixedSTTProvider("tell me something"),
            chat_service=CapturingChatService(provider=NamedProvider("openai")),
            tts_provider=CapturingTTSProvider(),
            voice_session=create_voice_session(),
            intent_runtime=IntentRuntime(tool_dispatcher=ToolDispatcher(registry=ToolRegistry())),
        )

        output = io.StringIO()
        with redirect_stdout(output):
            pipeline.run_once()

        debug_output = output.getvalue()
        self.assertIn("LLM Response", debug_output)
        self.assertIn("chat reply", debug_output)
        self.assertIn("(전체 길이 : 10 chars)", debug_output)
        self.assertIn("TTS Input", debug_output)
        self.assertIn("Length", debug_output)
        self.assertIn("\n10\n", debug_output)

    def test_tts_text_normalizer_removes_markdown(self):
        """Check Markdown is converted to plain text for TTS."""
        markdown_text = "\n".join(
            [
                "### 재료:",
                "**파스타**",
                "- 올리브 오일",
                "1. 물을 끓입니다.",
            ]
        )

        self.assertEqual(
            normalize_tts_text(markdown_text),
            "\n".join(
                [
                    "재료:",
                    "파스타",
                    "올리브 오일",
                    "1. 물을 끓입니다.",
                ]
            ),
        )

    def test_voice_pipeline_sends_normalized_text_to_tts(self):
        """Check TTS receives normalized text while response remains unchanged."""
        tts_provider = CapturingTTSProvider()
        chat_service = CapturingChatService(
            provider=NamedProvider("openai"),
            reply="### 재료:\n**파스타**\n- 올리브 오일",
        )
        pipeline = VoicePipeline(
            wake_listener=ImmediateWakeListener(),
            stt_provider=FixedSTTProvider("파스타 알려줘"),
            chat_service=chat_service,
            tts_provider=tts_provider,
            voice_session=create_voice_session(),
            intent_runtime=IntentRuntime(tool_dispatcher=ToolDispatcher(registry=ToolRegistry())),
        )

        output = io.StringIO()
        with redirect_stdout(output):
            reply = pipeline.run_once()

        self.assertEqual(reply, "### 재료:\n**파스타**\n- 올리브 오일")
        self.assertEqual(tts_provider.spoken, "재료:\n파스타\n올리브 오일")
        self.assertIn("TTS Input", output.getvalue())
        self.assertIn("재료:\n파스타\n올리브 오일", output.getvalue())


class EchoTool:
    """Safe echo test tool."""

    metadata = ToolMetadata(
        name="echo",
        description="Echo text.",
        domain="test",
        permission_level=PermissionLevel.SAFE,
        safe=True,
        capability="test.echo",
        aliases=["echo"],
        supported_intents=["test.echo"],
        input_mode="text",
        input_prefixes=["echo"],
    )

    def execute(self, input_data):
        """Return the text input."""
        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output=input_data.get("text", ""),
        )


class ImmediateWakeListener:
    """Wake listener that immediately continues."""

    def wait_for_wake_word(self):
        """Return immediately."""
        return None


class FixedSTTProvider:
    """STT test double."""

    def __init__(self, text):
        """Create an STT provider that returns fixed text."""
        self.text = text

    def listen(self):
        """Return fixed text."""
        return self.text


class CapturingChatService:
    """Chat service test double."""

    def __init__(self, provider=None, reply="chat reply"):
        """Create a chat capture."""
        self.messages = []
        self.provider = provider or object()
        self.reply = reply

    def generate_reply(self, message):
        """Record the message and return a reply."""
        self.messages.append(message)
        return self.reply


class CapturingTTSProvider:
    """TTS provider test double."""

    streaming_enabled = False

    def __init__(self):
        """Create a TTS capture."""
        self.spoken = None

    def speak(self, text):
        """Record spoken text."""
        self.spoken = text


class NamedProvider:
    """Provider test double with metadata."""

    def __init__(self, provider_name):
        """Create provider metadata."""
        self.last_metadata = NamedProviderMetadata(provider_name)


class NamedProviderMetadata:
    """Minimal provider metadata."""

    def __init__(self, provider_name):
        """Store provider name."""
        self.provider_name = provider_name


if __name__ == "__main__":
    unittest.main()
