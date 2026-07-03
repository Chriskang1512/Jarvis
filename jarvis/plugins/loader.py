from jarvis.plugins.builtin.echo import EchoPlugin
from jarvis.plugins.registry import PluginRegistry


class PluginLoader:
    """Load local and builtin plugins."""

    def __init__(self, diagnostics_collector=None):
        """Create a plugin loader."""
        self.diagnostics_collector = diagnostics_collector

    def load_builtin_plugins(self):
        """Load safe builtin plugins only."""
        return [EchoPlugin()]

    def load(self):
        """Load plugins into a plugin registry."""
        registry = PluginRegistry()

        for plugin in self.load_builtin_plugins():
            try:
                registry.register(plugin)
                self.log_event("plugin.loaded")
                if plugin.metadata.enabled:
                    self.log_event("plugin.enabled")
                else:
                    self.log_event("plugin.disabled")
            except Exception:
                self.log_event("plugin.failed")

        return registry

    def register_plugin_tools(self, plugin_registry, tool_registry):
        """Register enabled plugin tools into the ToolRegistry."""
        for plugin in plugin_registry.list_enabled():
            for tool in plugin.get_tools():
                tool_registry.register(tool)
                self.log_event("plugin.tool.registered")

    def log_event(self, message):
        """Publish plugin diagnostics event when available."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.log_event(message)
