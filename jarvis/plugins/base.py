from typing import Protocol

from jarvis.plugins.metadata import PluginMetadata


class Plugin(Protocol):
    """Common contract for Jarvis plugins."""

    metadata: PluginMetadata

    def get_tools(self):
        """Return tools exposed by this plugin."""
        ...
