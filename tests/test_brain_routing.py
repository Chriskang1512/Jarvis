import unittest
from dataclasses import dataclass, field

from jarvis.brain import BrainToolRouter
from jarvis.brain.controller import AGENT_KEYWORDS, find_agent_name
from jarvis.commands.chat import ChatCommand
from jarvis.memory import MemoryService, MockMemoryProvider
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolDispatcher, ToolMetadata, ToolResult, create_default_tool_registry
from jarvis.tools.registry import ToolRegistry


class TestBrainRouting(unittest.TestCase):
    """Test that Brain sends commands to the expected route."""

    def test_memory_has_highest_priority(self):
        """Check that memory commands beat investment keywords."""
        memory_keyword = AGENT_KEYWORDS["memory"][0]

        self.assertEqual(find_agent_name(f"{memory_keyword} VOO invest"), "memory")

    def test_invest_keywords(self):
        """Check that stock and ETF keywords go to Invest."""
        self.assertEqual(find_agent_name("SCHD dividend"), "invest")
        self.assertEqual(find_agent_name("VOO analysis"), "invest")
        self.assertEqual(find_agent_name("QQQ analysis"), "invest")

    def test_default_brain(self):
        """Check that unknown commands stay with Brain."""
        self.assertEqual(find_agent_name("how are you today"), "brain")

    def test_brain_tool_router_selects_calculator(self):
        """Check that Brain maps explicit arithmetic to the calculator tool."""
        registry = create_default_tool_registry()
        request = BrainToolRouter().plan("calculate 2 + 3 * 4", registry=registry)

        self.assertEqual(request.tool_name, "calculator")
        self.assertEqual(request.input_data["expression"], "2 + 3 * 4")

    def test_brain_tool_router_selects_time(self):
        """Check that Brain maps current-time requests to the time tool."""
        registry = create_default_tool_registry()
        request = BrainToolRouter().plan("what time is it", registry=registry)

        self.assertEqual(request.tool_name, "time")

    def test_brain_tool_router_selects_korean_time(self):
        """Check that Korean current-time requests route to the time tool."""
        registry = create_default_tool_registry()
        request = BrainToolRouter().plan("오늘 몇 시야", registry=registry)

        self.assertEqual(request.tool_name, "time")

    def test_brain_tool_router_selects_diagnostics(self):
        """Check that Brain maps diagnostics requests to the diagnostics tool."""
        registry = create_default_tool_registry()
        request = BrainToolRouter().plan("health check", registry=registry)

        self.assertEqual(request.tool_name, "diagnostics")

    def test_brain_tool_router_selects_memory_read(self):
        """Check that Brain maps memory requests to the memory read tool."""
        registry = create_default_tool_registry()
        request = BrainToolRouter().plan("recall user_name", registry=registry)

        self.assertEqual(request.tool_name, "memory_read")
        self.assertEqual(request.input_data["key"], "user_name")

    def test_brain_tool_router_ignores_ambiguous_chat(self):
        """Check that normal conversation still goes through chat."""
        registry = create_default_tool_registry()

        self.assertIsNone(
            BrainToolRouter().plan("tell me a story about focus", registry=registry)
        )

    def test_brain_tool_router_uses_registry_metadata_for_new_tools(self):
        """Check Brain can route a new safe tool without hardcoded tool knowledge."""
        registry = ToolRegistry()
        registry.register(UppercaseTool())

        request = BrainToolRouter().plan("uppercase hello", registry=registry)

        self.assertEqual(request.tool_name, "uppercase")
        self.assertEqual(request.input_data["text"], "hello")

    def test_brain_tool_router_skips_non_safe_tools(self):
        """Check automatic Brain routing only considers safe tools."""
        registry = ToolRegistry()
        registry.register(ConfirmUppercaseTool())

        request = BrainToolRouter().plan("uppercase hello", registry=registry)

        self.assertIsNone(request)

    def test_chat_command_executes_brain_tool_before_llm(self):
        """Check that natural tool requests do not call the chat provider."""
        provider = CapturingChatService()
        context = ChatCommandContext(
            chat_service=provider,
            tool_dispatcher=ToolDispatcher(create_default_tool_registry()),
            command_text="calculate 10 / 2",
        )

        output = ChatCommand().execute(context)

        self.assertEqual(output, "5.0")
        self.assertEqual(provider.messages, [])

    def test_chat_command_executes_memory_read_before_llm(self):
        """Check memory read requests execute through the tool path."""
        provider = CapturingChatService()
        memory_service = MemoryService(provider=MockMemoryProvider())
        memory_service.remember("user_name", "Chris")
        context = ChatCommandContext(
            chat_service=provider,
            tool_dispatcher=ToolDispatcher(
                create_default_tool_registry(memory_service=memory_service)
            ),
            command_text="recall user_name",
        )

        output = ChatCommand().execute(context)

        self.assertEqual(output, "Chris")
        self.assertEqual(provider.messages, [])

    def test_chat_command_falls_back_to_llm_for_normal_chat(self):
        """Check that non-tool requests still use ChatService."""
        provider = CapturingChatService()
        context = ChatCommandContext(
            chat_service=provider,
            tool_dispatcher=ToolDispatcher(create_default_tool_registry()),
            command_text="hello jarvis",
        )

        output = ChatCommand().execute(context)

        self.assertEqual(output, "chat reply")
        self.assertEqual(provider.messages, ["hello jarvis"])


class NullEventBus:
    """Event bus used by chat command tests."""

    def publish_state(self, event_type, state):
        """Ignore published command state."""
        return None


class CapturingChatService:
    """Chat service test double that records messages."""

    def __init__(self):
        """Create an empty message capture."""
        self.messages = []

    def generate_reply(self, message):
        """Record the message and return a deterministic reply."""
        self.messages.append(message)
        return "chat reply"


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


class ConfirmUppercaseTool(UppercaseTool):
    """Confirm-required metadata-routed test tool."""

    metadata = ToolMetadata(
        name="confirm_uppercase",
        description="Uppercase text after confirmation.",
        domain="test",
        permission_level=PermissionLevel.CONFIRM,
        safe=False,
        capability="test.uppercase",
        aliases=["uppercase"],
        supported_intents=["uppercase"],
        input_mode="text",
        input_prefixes=["uppercase"],
    )


@dataclass
class ChatCommandContext:
    """Minimal context for ChatCommand tests."""

    chat_service: object
    tool_dispatcher: object
    command_text: str
    event_bus: object = field(default_factory=NullEventBus)


if __name__ == "__main__":
    unittest.main()
