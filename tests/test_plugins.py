import unittest

from jarvis.diagnostics import DiagnosticsCollector
from jarvis.permissions import PermissionLevel
from jarvis.plugins import PluginLoader, PluginMetadata, PluginRegistry
from jarvis.plugins.builtin.echo import EchoPlugin
from jarvis.tools import ToolDispatcher, ToolRequest
from jarvis.tools.registry import ToolRegistry


class TestPlugins(unittest.TestCase):
    """Test plugin system foundation."""

    def test_plugin_metadata_model(self):
        """Check plugin metadata carries future plugin fields."""
        metadata = PluginMetadata(
            id="test.plugin",
            name="Test Plugin",
            version="0.1.0",
            domain="core",
            description="Test plugin.",
            author="Tester",
            enabled=True,
            permission_level=PermissionLevel.SAFE,
        )

        self.assertEqual(metadata.id, "test.plugin")
        self.assertEqual(metadata.domain, "core")
        self.assertTrue(metadata.enabled)
        self.assertEqual(metadata.permission_level, PermissionLevel.SAFE)

    def test_plugin_registry_lists_plugins(self):
        """Check plugin registry lookup APIs."""
        registry = PluginRegistry()
        plugin = EchoPlugin()

        registry.register(plugin)

        self.assertIs(registry.get_plugin("builtin.echo"), plugin)
        self.assertEqual(registry.list_plugins(), [plugin])
        self.assertEqual(registry.list_enabled(), [plugin])
        self.assertEqual(registry.list_by_domain("core"), [plugin])

    def test_loader_loads_builtin_plugins(self):
        """Check loader discovers builtin plugins."""
        registry = PluginLoader().load()

        self.assertIsNotNone(registry.get_plugin("builtin.echo"))

    def test_plugin_tools_register_into_tool_registry(self):
        """Check plugin tools register into the shared ToolRegistry."""
        plugin_loader = PluginLoader()
        plugin_registry = plugin_loader.load()
        tool_registry = ToolRegistry()

        plugin_loader.register_plugin_tools(plugin_registry, tool_registry)

        self.assertTrue(tool_registry.exists("plugin_echo"))

    def test_plugin_tool_runs_through_dispatcher_permission_flow(self):
        """Check plugin tools execute through the standard dispatcher."""
        plugin_loader = PluginLoader()
        plugin_registry = plugin_loader.load()
        tool_registry = ToolRegistry()
        plugin_loader.register_plugin_tools(plugin_registry, tool_registry)
        dispatcher = ToolDispatcher(registry=tool_registry)

        result = dispatcher.execute(
            ToolRequest(
                tool_name="plugin_echo",
                input_data={"text": "hello plugin"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, "hello plugin")

    def test_plugin_diagnostics_events(self):
        """Check plugin loader publishes diagnostics events."""
        diagnostics = DiagnosticsCollector()
        plugin_loader = PluginLoader(diagnostics_collector=diagnostics)
        plugin_registry = plugin_loader.load()
        plugin_loader.register_plugin_tools(plugin_registry, ToolRegistry())

        messages = [event.message for event in diagnostics.get_snapshot().events]
        self.assertIn("plugin.loaded", messages)
        self.assertIn("plugin.enabled", messages)
        self.assertIn("plugin.tool.registered", messages)


if __name__ == "__main__":
    unittest.main()
