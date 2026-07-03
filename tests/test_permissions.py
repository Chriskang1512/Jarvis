import unittest

from jarvis.diagnostics import DiagnosticsCollector
from jarvis.permissions import PermissionLayer, PermissionLevel, PermissionStatus
from jarvis.tools import ToolDispatcher, ToolMetadata, ToolRequest, ToolResult
from jarvis.tools.registry import ToolRegistry


class RecordingTool:
    """Tool used to check permission behavior."""

    def __init__(self, permission_level):
        """Create a tool with one permission level."""
        self.was_executed = False
        self.metadata = ToolMetadata(
            name=f"{permission_level.value}_tool",
            description="Permission test tool.",
            permission_level=permission_level,
        )

    def execute(self, input_data):
        """Record execution and return success."""
        self.was_executed = True
        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output="executed",
        )


class TestPermissions(unittest.TestCase):
    """Test the Guardian permission layer."""

    def test_permission_layer_allows_safe_tools(self):
        """Check SAFE tools are allowed."""
        tool = RecordingTool(PermissionLevel.SAFE)
        decision = PermissionLayer().evaluate(tool)

        self.assertEqual(decision.status, PermissionStatus.ALLOWED)
        self.assertTrue(decision.allowed)

    def test_permission_layer_requires_confirmation(self):
        """Check CONFIRM tools return a structured confirmation decision."""
        tool = RecordingTool(PermissionLevel.CONFIRM)
        decision = PermissionLayer().evaluate(tool)

        self.assertEqual(decision.status, PermissionStatus.CONFIRM_REQUIRED)
        self.assertFalse(decision.allowed)

    def test_permission_layer_denies_restricted_tools(self):
        """Check RESTRICTED tools are denied."""
        tool = RecordingTool(PermissionLevel.RESTRICTED)
        decision = PermissionLayer().evaluate(tool)

        self.assertEqual(decision.status, PermissionStatus.DENIED)
        self.assertFalse(decision.allowed)

    def test_dispatcher_blocks_confirm_tool_before_execution(self):
        """Check dispatcher does not execute confirm-required tools."""
        tool = RecordingTool(PermissionLevel.CONFIRM)
        registry = create_registry_with_tool(tool)
        dispatcher = ToolDispatcher(registry=registry)

        result = dispatcher.execute(ToolRequest(tool_name=tool.metadata.name))

        self.assertFalse(result.success)
        self.assertIn("confirmation required", result.error)
        self.assertFalse(tool.was_executed)

    def test_dispatcher_blocks_restricted_tool_before_execution(self):
        """Check dispatcher does not execute restricted tools."""
        tool = RecordingTool(PermissionLevel.RESTRICTED)
        registry = create_registry_with_tool(tool)
        dispatcher = ToolDispatcher(registry=registry)

        result = dispatcher.execute(ToolRequest(tool_name=tool.metadata.name))

        self.assertFalse(result.success)
        self.assertIn("Permission denied", result.error)
        self.assertFalse(tool.was_executed)

    def test_permission_diagnostics_events(self):
        """Check permission decisions publish diagnostics events."""
        diagnostics = DiagnosticsCollector()
        tool = RecordingTool(PermissionLevel.CONFIRM)

        PermissionLayer(diagnostics_collector=diagnostics).evaluate(tool)

        messages = [event.message for event in diagnostics.get_snapshot().events]
        self.assertIn("permission.check.started", messages)
        self.assertIn("permission.confirm.required", messages)


def create_registry_with_tool(tool):
    """Create a registry containing one test tool."""
    registry = ToolRegistry()
    registry.register(tool)
    return registry


if __name__ == "__main__":
    unittest.main()
