import unittest

from jarvis.brain import BrainToolRouter
from jarvis.capabilities import CapabilityLoader, CapabilityMetadata, CapabilityRegistry
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolDispatcher, ToolMetadata, ToolRequest, ToolResult
from jarvis.tools.registry import ToolRegistry


class TestCapabilities(unittest.TestCase):
    """Test capability plugin framework."""

    def test_capability_metadata_model(self):
        """Check capability metadata carries extension fields."""
        metadata = CapabilityMetadata(
            id="finance",
            name="Finance",
            description="Financial assistant.",
            version="0.1.0-alpha",
            status="alpha",
            owner="Jarvis Team",
            enabled=True,
            permission_level=PermissionLevel.SAFE,
            tools=["exchange_rate"],
        )

        self.assertEqual(metadata.id, "finance")
        self.assertEqual(metadata.name, "Finance")
        self.assertEqual(metadata.status, "alpha")
        self.assertEqual(metadata.owner, "Jarvis Team")
        self.assertTrue(metadata.enabled)
        self.assertEqual(metadata.tools, ["exchange_rate"])

    def test_loader_discovers_builtin_capability_skeletons(self):
        """Check loader automatically discovers installed capabilities."""
        registry = CapabilityLoader().load()
        capability_ids = [capability.metadata.id for capability in registry.list()]

        self.assertEqual(
            capability_ids,
            ["creator", "finance", "hotel", "japanese", "life"],
        )

    def test_registry_rejects_duplicate_capability_ids(self):
        """Check duplicate capability IDs fail loudly."""
        registry = CapabilityRegistry()
        registry.register(ExampleCapability())

        with self.assertRaises(ValueError):
            registry.register(ExampleCapability())

    def test_enabled_capability_registers_tools(self):
        """Check enabled capability tools register into ToolRegistry."""
        registry = CapabilityRegistry()
        registry.register(ExampleCapability())
        tool_registry = ToolRegistry()

        registry.register_tools(tool_registry)

        self.assertTrue(tool_registry.exists("example_echo"))

    def test_disabled_capability_does_not_register_tools(self):
        """Check disabled capabilities are excluded from tool registration."""
        registry = CapabilityRegistry()
        registry.register(DisabledExampleCapability())
        tool_registry = ToolRegistry()

        registry.register_tools(tool_registry)

        self.assertFalse(tool_registry.exists("disabled_echo"))

    def test_disabled_capability_has_no_router_candidate(self):
        """Check disabled capability tools never reach Brain routing."""
        registry = CapabilityRegistry()
        registry.register(DisabledExampleCapability())
        tool_registry = ToolRegistry()
        registry.register_tools(tool_registry)

        request = BrainToolRouter().plan("disabled hello", registry=tool_registry)

        self.assertIsNone(request)

    def test_registry_lifecycle_enable_disable_remove_upgrade(self):
        """Check capability lifecycle APIs for alpha operations."""
        registry = CapabilityRegistry()
        registry.register(ExampleCapability())

        self.assertTrue(registry.disable("example"))
        self.assertEqual(registry.list_enabled(), [])
        self.assertTrue(registry.enable("example"))
        self.assertEqual(registry.list_enabled()[0].metadata.id, "example")

        registry.upgrade(ExampleCapabilityV2())
        self.assertEqual(registry.get("example").metadata.version, "0.2.0")
        self.assertTrue(registry.remove("example"))
        self.assertFalse(registry.exists("example"))

    def test_capability_tool_runs_through_dispatcher(self):
        """Check capability tools use the existing dispatcher and permission flow."""
        registry = CapabilityRegistry()
        registry.register(ExampleCapability())
        tool_registry = ToolRegistry()
        registry.register_tools(tool_registry)
        dispatcher = ToolDispatcher(registry=tool_registry)

        result = dispatcher.execute(
            ToolRequest(
                tool_name="example_echo",
                input_data={"text": "hello capability"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, "hello capability")

    def test_brain_routes_capability_tool_from_registry_metadata(self):
        """Check Brain needs no change when a capability adds a metadata tool."""
        registry = CapabilityRegistry()
        registry.register(ExampleCapability())
        tool_registry = ToolRegistry()
        registry.register_tools(tool_registry)

        request = BrainToolRouter().plan("example hello", registry=tool_registry)

        self.assertEqual(request.tool_name, "example_echo")
        self.assertEqual(request.input_data["text"], "hello")

    def test_router_skips_deprecated_tools(self):
        """Check deprecated tools are not automatic router candidates."""
        tool_registry = ToolRegistry()
        tool_registry.register(DeprecatedEchoTool())

        request = BrainToolRouter().plan("deprecated hello", registry=tool_registry)

        self.assertIsNone(request)

    def test_router_uses_priority_to_break_score_ties(self):
        """Check route priority breaks equal score matches."""
        tool_registry = ToolRegistry()
        tool_registry.register(LowPriorityEchoTool())
        tool_registry.register(HighPriorityEchoTool())

        request = BrainToolRouter().plan("priority hello", registry=tool_registry)

        self.assertEqual(request.tool_name, "high_priority_echo")

    def test_capability_diagnostics_events(self):
        """Check capability loader publishes lifecycle diagnostics."""
        diagnostics = DiagnosticsCollector()
        loader = CapabilityLoader(diagnostics_collector=diagnostics)
        registry = loader.load()
        loader.register_capability_tools(registry, ToolRegistry())

        messages = [event.message for event in diagnostics.get_snapshot().events]
        self.assertIn("capability.loaded", messages)
        self.assertIn("capability.enabled", messages)


class ExampleCapability:
    """Test capability with one safe tool."""

    metadata = CapabilityMetadata(
        id="example",
        name="Example",
        description="Example capability.",
        version="0.1.0",
        enabled=True,
        tools=["example_echo"],
    )

    def get_tools(self):
        """Return tools owned by this capability."""
        return [ExampleEchoTool()]


class ExampleCapabilityV2(ExampleCapability):
    """Newer test capability for lifecycle upgrade."""

    metadata = CapabilityMetadata(
        id="example",
        name="Example",
        description="Example capability.",
        version="0.2.0",
        enabled=True,
        tools=["example_echo"],
    )


class DisabledExampleCapability:
    """Disabled test capability."""

    metadata = CapabilityMetadata(
        id="disabled_example",
        name="Disabled Example",
        description="Disabled capability.",
        version="0.1.0",
        enabled=False,
        tools=["disabled_echo"],
    )

    def get_tools(self):
        """Return tools owned by this capability."""
        return [DisabledEchoTool()]


class ExampleEchoTool:
    """Safe test tool owned by a capability."""

    metadata = ToolMetadata(
        name="example_echo",
        description="Echo example text.",
        domain="example",
        permission_level=PermissionLevel.SAFE,
        safe=True,
        capability="example.echo",
        aliases=["example"],
        supported_intents=["example"],
        input_mode="text",
        input_prefixes=["example"],
    )

    def execute(self, input_data):
        """Return the provided text."""
        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output=str(input_data.get("text", "")),
        )


class DisabledEchoTool(ExampleEchoTool):
    """Disabled capability tool."""

    metadata = ToolMetadata(
        name="disabled_echo",
        description="Echo disabled text.",
        domain="example",
        permission_level=PermissionLevel.SAFE,
        safe=True,
        capability="example.disabled_echo",
        aliases=["disabled"],
        supported_intents=["disabled"],
        input_mode="text",
        input_prefixes=["disabled"],
    )


class DeprecatedEchoTool(ExampleEchoTool):
    """Deprecated tool that should not be auto-routed."""

    metadata = ToolMetadata(
        name="deprecated_echo",
        description="Deprecated echo text.",
        domain="example",
        permission_level=PermissionLevel.SAFE,
        safe=True,
        deprecated=True,
        capability="example.deprecated_echo",
        aliases=["deprecated"],
        supported_intents=["deprecated"],
        input_mode="text",
        input_prefixes=["deprecated"],
    )


class LowPriorityEchoTool(ExampleEchoTool):
    """Low priority tool for tie-break tests."""

    metadata = ToolMetadata(
        name="low_priority_echo",
        description="Low priority echo text.",
        domain="example",
        permission_level=PermissionLevel.SAFE,
        safe=True,
        priority=1,
        capability="example.priority_echo",
        aliases=["priority"],
        supported_intents=["priority"],
        input_mode="text",
        input_prefixes=["priority"],
    )


class HighPriorityEchoTool(ExampleEchoTool):
    """High priority tool for tie-break tests."""

    metadata = ToolMetadata(
        name="high_priority_echo",
        description="High priority echo text.",
        domain="example",
        permission_level=PermissionLevel.SAFE,
        safe=True,
        priority=10,
        capability="example.priority_echo",
        aliases=["priority"],
        supported_intents=["priority"],
        input_mode="text",
        input_prefixes=["priority"],
    )


if __name__ == "__main__":
    unittest.main()
