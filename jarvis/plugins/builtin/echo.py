from jarvis.permissions import PermissionLevel
from jarvis.plugins.metadata import PluginMetadata
from jarvis.tools import ToolMetadata, ToolResult


class EchoPlugin:
    """Builtin plugin used to validate plugin loading."""

    metadata = PluginMetadata(
        id="builtin.echo",
        name="Echo",
        version="0.1.0",
        domain="core",
        description="Builtin plugin that exposes a safe echo tool.",
        author="Jarvis",
        enabled=True,
        permission_level=PermissionLevel.SAFE,
    )

    def get_tools(self):
        """Return plugin tools."""
        return [EchoTool()]


class EchoTool:
    """Safe plugin tool that echoes input text."""

    metadata = ToolMetadata(
        name="plugin_echo",
        description="Echo text through the builtin plugin system.",
        domain="plugins",
        permission_level=PermissionLevel.SAFE,
        safe=True,
    )

    def execute(self, input_data):
        """Return the provided text."""
        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output=str(input_data.get("text", "")),
        )
