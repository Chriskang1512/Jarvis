import unittest

from jarvis.commands.tool import parse_tool_command
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.memory import MemoryService, MockMemoryProvider
from jarvis.tools import ToolDispatcher, ToolRequest, ToolResult, create_default_tool_registry
from jarvis.tools.safe_tools import evaluate_expression


class TestTools(unittest.TestCase):
    """Test the safe Tool Calling framework."""

    def test_default_registry_contains_safe_tools(self):
        """Check that built-in tools are registered by name."""
        registry = create_default_tool_registry()

        self.assertTrue(registry.exists("time"))
        self.assertTrue(registry.exists("calculator"))
        self.assertTrue(registry.exists("diagnostics"))
        self.assertTrue(registry.exists("memory_read"))

    def test_registry_lists_tools_by_domain(self):
        """Check that tools can be discovered by domain."""
        registry = create_default_tool_registry()

        core_tool_names = [tool.metadata.name for tool in registry.list_by_domain("core")]
        memory_tool_names = [tool.metadata.name for tool in registry.list_by_domain("memory")]

        self.assertIn("time", core_tool_names)
        self.assertIn("calculator", core_tool_names)
        self.assertIn("diagnostics", core_tool_names)
        self.assertIn("memory_read", memory_tool_names)
        self.assertEqual(registry.list_domains(), ["core", "memory"])

    def test_dispatcher_executes_calculator_tool(self):
        """Check that dispatcher executes a registered safe tool."""
        registry = create_default_tool_registry()
        dispatcher = ToolDispatcher(registry=registry)

        result = dispatcher.execute(
            ToolRequest(
                tool_name="calculator",
                input_data={"expression": "2 + 3 * 4"},
            )
        )

        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.success)
        self.assertEqual(result.output, 14)

    def test_dispatcher_returns_failure_for_unknown_tool(self):
        """Check that unknown tools fail safely."""
        registry = create_default_tool_registry()
        dispatcher = ToolDispatcher(registry=registry)

        result = dispatcher.execute(ToolRequest(tool_name="missing"))

        self.assertFalse(result.success)
        self.assertIn("not registered", result.error)

    def test_dispatcher_publishes_diagnostics_events(self):
        """Check tool lifecycle diagnostics events."""
        diagnostics = DiagnosticsCollector()
        registry = create_default_tool_registry(diagnostics_collector=diagnostics)
        dispatcher = ToolDispatcher(
            registry=registry,
            diagnostics_collector=diagnostics,
        )

        dispatcher.execute(ToolRequest(tool_name="time"))

        messages = [event.message for event in diagnostics.get_snapshot().events]
        self.assertIn("tool.requested", messages)
        self.assertIn("tool.selected", messages)
        self.assertIn("tool.started", messages)
        self.assertIn("tool.completed", messages)

    def test_calculator_rejects_unsafe_expression(self):
        """Check calculator does not execute arbitrary Python."""
        with self.assertRaises(ValueError):
            evaluate_expression("__import__('os').system('echo bad')")

    def test_calculator_rejects_expensive_expression(self):
        """Check calculator keeps arithmetic bounded."""
        with self.assertRaises(ValueError):
            evaluate_expression("2 ** 999")

    def test_memory_read_tool_reads_memory_service(self):
        """Check that memory_read safely reads through MemoryService."""
        memory_service = MemoryService(provider=MockMemoryProvider())
        memory_service.remember("user_name", "Chris")
        registry = create_default_tool_registry(memory_service=memory_service)
        dispatcher = ToolDispatcher(registry=registry)

        result = dispatcher.execute(
            ToolRequest(
                tool_name="memory_read",
                input_data={"key": "user_name"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, "Chris")

    def test_tool_command_parser_maps_safe_inputs(self):
        """Check CLI tool command text becomes structured input."""
        tool_name, input_data = parse_tool_command("calculator 1 + 2")

        self.assertEqual(tool_name, "calculator")
        self.assertEqual(input_data["expression"], "1 + 2")


if __name__ == "__main__":
    unittest.main()
