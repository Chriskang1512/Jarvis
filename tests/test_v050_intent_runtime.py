import unittest
import inspect
from dataclasses import FrozenInstanceError

from jarvis.brain import Intent, IntentParser, IntentRuntime, RuntimeContext, RuntimeResult
from jarvis.brain import intent_runtime as intent_runtime_module
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.diagnostics.console import DiagnosticsConsole
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolDispatcher, ToolMetadata, ToolRequest, ToolResult, create_default_tool_registry
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.router import ToolRoute
from jarvis.voice.pipeline import VoicePipeline


class TestV050IntentRuntime(unittest.TestCase):
    """Test the v0.5 Voice -> Intent -> Tool -> Permission pipeline."""

    def test_intent_parser_detects_korean_time_lookup_after_wake_word(self):
        """Check wake-word input becomes a time.lookup intent."""
        registry = create_default_tool_registry()

        intent = IntentParser().parse("\uc790\ube44\uc2a4, \uc9c0\uae08 \uba87 \uc2dc\uc57c?", registry)

        self.assertIsInstance(intent, Intent)
        self.assertEqual(intent.name, "time.lookup")
        self.assertEqual(intent.tool_name, "time")
        self.assertEqual(intent.source, "keyword")
        self.assertEqual(intent.parameters, {})
        self.assertEqual(intent.raw_text, "\uc9c0\uae08 \uba87 \uc2dc\uc57c?")

        with self.assertRaises(FrozenInstanceError):
            intent.name = "weather.lookup"

        with self.assertRaises(TypeError):
            intent.parameters["city"] = "Seoul"

    def test_runtime_accepts_context_object(self):
        """Check RuntimeContext is the preferred runtime input contract."""
        diagnostics = DiagnosticsCollector()
        dispatcher = ToolDispatcher(
            registry=create_default_tool_registry(diagnostics_collector=diagnostics),
            diagnostics_collector=diagnostics,
        )
        runtime = IntentRuntime(tool_dispatcher=dispatcher, diagnostics_collector=diagnostics)
        context = RuntimeContext(
            text="what time is it",
            source="api",
            language="en",
            session_id="session_1",
            user_id="user_1",
            wake_word="jarvis",
            conversation_id="conv_1",
            timestamp="2026-07-04T12:00:00",
        )

        result = runtime.run(context)

        self.assertTrue(result.success)
        self.assertEqual(result.diagnostics.input_source, "api")
        self.assertEqual(result.diagnostics.context.session_id, "session_1")
        self.assertEqual(result.diagnostics.context.user_id, "user_1")
        self.assertEqual(result.diagnostics.context.timestamp, "2026-07-04T12:00:00")

    def test_intent_runtime_executes_safe_tool_and_publishes_diagnostics(self):
        """Check safe intents execute and diagnostics records every major step."""
        diagnostics = DiagnosticsCollector()
        dispatcher = ToolDispatcher(
            registry=create_default_tool_registry(diagnostics_collector=diagnostics),
            diagnostics_collector=diagnostics,
        )
        runtime = IntentRuntime(
            tool_dispatcher=dispatcher,
            diagnostics_collector=diagnostics,
        )

        result = runtime.handle("what time is it")

        snapshot = diagnostics.get_snapshot()
        self.assertIsInstance(result, RuntimeResult)
        self.assertTrue(result.handled)
        self.assertTrue(result.success)
        self.assertEqual(result.intent.name, "time.lookup")
        self.assertEqual(result.permission_status, "allowed")
        self.assertEqual(result.tool, "time")
        self.assertGreaterEqual(result.elapsed, 0.0)
        self.assertEqual(result.diagnostics.input_source, "text")
        self.assertEqual(snapshot.intent_runtime.input_text, "what time is it")
        self.assertEqual(snapshot.intent_runtime.detected_intent, "time.lookup")
        self.assertEqual(snapshot.intent_runtime.selected_tool, "time")
        self.assertEqual(snapshot.intent_runtime.permission_status, "allowed")
        self.assertEqual(snapshot.intent_runtime.execution_result, "success")
        self.assertNotEqual(snapshot.intent_runtime.response, "")
        self.assertIn(
            "runtime.completed",
            [event.event_type for event in snapshot.published_events],
        )

    def test_runtime_publishes_stage_events(self):
        """Check runtime emits events for diagnostics, replay, and analytics."""
        diagnostics = DiagnosticsCollector()
        dispatcher = ToolDispatcher(
            registry=create_default_tool_registry(diagnostics_collector=diagnostics),
            diagnostics_collector=diagnostics,
        )
        runtime = IntentRuntime(tool_dispatcher=dispatcher, diagnostics_collector=diagnostics)

        runtime.run(RuntimeContext(text="what time is it", source="cli"))

        event_types = [event.event_type for event in diagnostics.get_snapshot().published_events]
        self.assertIn("runtime.started", event_types)
        self.assertIn("intent.parsed", event_types)
        self.assertIn("permission.checked", event_types)
        self.assertIn("tool.executed", event_types)
        self.assertIn("response.generated", event_types)
        self.assertIn("runtime.completed", event_types)
        self.assertIn("runtime.finished", event_types)

    def test_intent_runtime_stops_confirm_tool_before_execution(self):
        """Check confirm-required intents produce a confirmation response."""
        diagnostics = DiagnosticsCollector()
        tool = ConfirmEmailTool()
        registry = ToolRegistry()
        registry.register(tool)
        dispatcher = ToolDispatcher(registry=registry, diagnostics_collector=diagnostics)
        runtime = IntentRuntime(tool_dispatcher=dispatcher, diagnostics_collector=diagnostics)

        result = runtime.handle("send email hello")

        self.assertTrue(result.handled)
        self.assertFalse(result.success)
        self.assertFalse(tool.was_executed)
        self.assertEqual(result.intent.name, "email.send")
        self.assertEqual(result.permission_status, "confirm_required")
        self.assertIn("\ud655\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4", result.response)

    def test_permission_runs_before_router(self):
        """Check denied intents do not ask the router to select a tool."""
        registry = ToolRegistry()
        registry.register(RestrictedDeleteTool())
        dispatcher = ToolDispatcher(registry=registry)
        router = FailingRouter()
        runtime = IntentRuntime(tool_dispatcher=dispatcher, tool_router=router)

        result = runtime.run("delete files now", input_source="api")

        self.assertTrue(result.handled)
        self.assertFalse(result.success)
        self.assertEqual(result.permission_status, "denied")
        self.assertFalse(router.was_called)

    def test_runtime_depends_on_tool_router_contract_not_brain_router(self):
        """Check Runtime does not import or name BrainToolRouter."""
        source = inspect.getsource(intent_runtime_module)

        self.assertNotIn("jarvis.brain.tool_router", source)
        self.assertNotIn("BrainToolRouter", source)
        self.assertIn("resolve_tool_route", source)

    def test_runtime_executes_with_resolve_only_router(self):
        """Check Runtime only needs router.resolve(intent)."""
        registry = ToolRegistry()
        tool = UppercaseTool()
        registry.register(tool)
        dispatcher = ToolDispatcher(registry=registry)
        runtime = IntentRuntime(
            tool_dispatcher=dispatcher,
            tool_router=ResolveOnlyRouter(tool),
        )

        result = runtime.run("uppercase hello", input_source="plugin")

        self.assertTrue(result.success)
        self.assertEqual(result.tool, "uppercase")
        self.assertEqual(result.response, "HELLO")

    def test_runtime_is_source_agnostic_for_text_cli_api(self):
        """Check Text, CLI, and API inputs use the same runtime engine."""
        diagnostics = DiagnosticsCollector()
        dispatcher = ToolDispatcher(
            registry=create_default_tool_registry(diagnostics_collector=diagnostics),
            diagnostics_collector=diagnostics,
        )
        runtime = IntentRuntime(tool_dispatcher=dispatcher, diagnostics_collector=diagnostics)

        for source in ["text", "cli", "api"]:
            result = runtime.run("what time is it", input_source=source)
            self.assertTrue(result.success)
            self.assertEqual(result.diagnostics.input_source, source)

    def test_runtime_routes_bare_arithmetic_expression(self):
        """Check runtime keeps calculator parity with BrainToolRouter."""
        dispatcher = ToolDispatcher(registry=create_default_tool_registry())
        runtime = IntentRuntime(tool_dispatcher=dispatcher)

        result = runtime.run("2 + 3 * 4", input_source="text")

        self.assertTrue(result.success)
        self.assertEqual(result.intent.name, "math.calculate")
        self.assertEqual(result.tool, "calculator")
        self.assertEqual(result.response, "14")

    def test_permission_layer_allows_confirm_tool_after_approval_flag(self):
        """Check confirm-required tools can execute after explicit approval."""
        tool = ConfirmEmailTool()
        registry = ToolRegistry()
        registry.register(tool)
        dispatcher = ToolDispatcher(registry=registry)

        result = dispatcher.execute(
            ToolRequest(
                tool_name="email_send",
                input_data={
                    "text": "hello",
                    "_confirmed": True,
                },
            )
        )

        self.assertTrue(result.success)
        self.assertTrue(tool.was_executed)

    def test_voice_pipeline_uses_intent_runtime_before_chat_service(self):
        """Check STT can flow through intent runtime into TTS without LLM."""
        diagnostics = DiagnosticsCollector()
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        dispatcher = ToolDispatcher(
            registry=create_default_tool_registry(diagnostics_collector=diagnostics),
            diagnostics_collector=diagnostics,
        )
        runtime = IntentRuntime(tool_dispatcher=dispatcher, diagnostics_collector=diagnostics)
        pipeline = VoicePipeline(
            wake_listener=ImmediateWakeListener(),
            stt_provider=FixedSTTProvider("\uc790\ube44\uc2a4, \uc9c0\uae08 \uba87 \uc2dc\uc57c?"),
            chat_service=chat_service,
            tts_provider=tts_provider,
            diagnostics_collector=diagnostics,
            intent_runtime=runtime,
        )

        reply = pipeline.run_once()

        snapshot = diagnostics.get_snapshot()
        self.assertNotEqual(reply, "")
        self.assertEqual(chat_service.messages, [])
        self.assertEqual(tts_provider.spoken, reply)
        self.assertEqual(snapshot.intent_runtime.detected_intent, "time.lookup")
        self.assertEqual(snapshot.intent_runtime.input_source, "voice")
        self.assertEqual(snapshot.intent_runtime.tts_output, "yes")
        self.assertIn("Intent Runtime", DiagnosticsConsole().render(snapshot))

    def test_voice_pipeline_does_not_send_stt_errors_to_llm_or_tts(self):
        """Check STT failure text stops before fallback chat and TTS."""
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        dispatcher = ToolDispatcher(registry=create_default_tool_registry())
        runtime = IntentRuntime(tool_dispatcher=dispatcher)
        pipeline = VoicePipeline(
            wake_listener=ImmediateWakeListener(),
            stt_provider=FixedSTTProvider("Speech recognition failed: unknown value"),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
        )

        reply = pipeline.run_once()

        self.assertEqual(reply, "")
        self.assertEqual(chat_service.messages, [])
        self.assertIsNone(tts_provider.spoken)


class ConfirmEmailTool:
    """Confirm-required test tool."""

    metadata = ToolMetadata(
        name="email_send",
        description="Send an email.",
        domain="email",
        permission_level=PermissionLevel.CONFIRM,
        safe=False,
        capability="email.send",
        aliases=["send email"],
        supported_intents=["email.send"],
        input_mode="text",
        input_prefixes=["send email"],
    )

    def __init__(self):
        """Create a non-executed test tool."""
        self.was_executed = False

    def execute(self, input_data):
        """Record execution."""
        self.was_executed = True
        return ToolResult(tool_name=self.metadata.name, success=True, output="sent")


class RestrictedDeleteTool:
    """Restricted test tool."""

    metadata = ToolMetadata(
        name="delete_files",
        description="Delete files.",
        domain="file",
        permission_level=PermissionLevel.RESTRICTED,
        safe=False,
        capability="file.delete",
        aliases=["delete files"],
        supported_intents=["file.delete"],
        input_mode="text",
        input_prefixes=["delete files"],
    )

    def execute(self, input_data):
        """This should not run in the test."""
        return ToolResult(tool_name=self.metadata.name, success=True, output="deleted")


class UppercaseTool:
    """Safe metadata-routed test tool."""

    metadata = ToolMetadata(
        name="uppercase",
        description="Uppercase text.",
        domain="test",
        permission_level=PermissionLevel.SAFE,
        safe=True,
        capability="test.uppercase",
        aliases=["uppercase"],
        supported_intents=["uppercase"],
        input_mode="text",
        input_prefixes=["uppercase"],
    )

    def execute(self, input_data):
        """Return uppercased text."""
        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output=str(input_data.get("text", "")).upper(),
        )


class ResolveOnlyRouter:
    """Router test double that exposes only resolve."""

    def __init__(self, tool):
        """Create a router for one tool."""
        self.tool = tool

    def resolve(self, intent):
        """Resolve one test intent."""
        return ToolRoute(
            tool_name=self.tool.metadata.name,
            input_data=dict(intent.parameters),
            tool=self.tool,
        )


class FailingRouter:
    """Router that records whether it was called."""

    def __init__(self):
        """Create a router spy."""
        self.was_called = False

    def route(self, intent):
        """Legacy route should not be called by Runtime."""
        raise AssertionError("Runtime should only call resolve(intent).")

    def resolve(self, intent):
        """Record calls and fail if permission ordering is wrong."""
        self.was_called = True
        raise AssertionError("Router should not run before permission denial.")


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

    def __init__(self):
        """Create a chat capture."""
        self.messages = []
        self.provider = object()

    def generate_reply(self, message):
        """Record the message and return a reply."""
        self.messages.append(message)
        return "chat reply"


class CapturingTTSProvider:
    """TTS provider test double."""

    streaming_enabled = False

    def __init__(self):
        """Create a TTS capture."""
        self.spoken = None

    def speak(self, text):
        """Record spoken text."""
        self.spoken = text


if __name__ == "__main__":
    unittest.main()
