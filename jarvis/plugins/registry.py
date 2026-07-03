class PluginRegistry:
    """Store and look up loaded plugins."""

    def __init__(self):
        """Create an empty plugin registry."""
        self.plugins = {}

    def register(self, plugin):
        """Register one plugin by ID."""
        self.plugins[plugin.metadata.id] = plugin

    def get_plugin(self, plugin_id):
        """Return one plugin by ID."""
        return self.plugins.get(plugin_id)

    def list_plugins(self):
        """Return all plugins sorted by ID."""
        return [self.plugins[plugin_id] for plugin_id in sorted(self.plugins)]

    def list_by_domain(self, domain):
        """Return plugins in one domain."""
        return [
            plugin
            for plugin in self.list_plugins()
            if plugin.metadata.domain == domain
        ]

    def list_enabled(self):
        """Return enabled plugins."""
        return [
            plugin
            for plugin in self.list_plugins()
            if plugin.metadata.enabled
        ]
