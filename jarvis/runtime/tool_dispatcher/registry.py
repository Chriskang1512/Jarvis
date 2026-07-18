class RuntimeToolRegistry:
    """Registry facade with priority-aware listing."""

    def __init__(self, registry):
        """Wrap an existing ToolRegistry."""
        self.registry = registry

    def get(self, tool_name):
        """Return one tool."""
        return self.registry.get(tool_name)

    def list(self):
        """Return tools ordered by priority and name."""
        return sorted(
            self.registry.list(),
            key=lambda tool: (getattr(tool.metadata, "priority", 0), tool.metadata.name),
            reverse=True,
        )

    def exists(self, tool_name):
        """Return whether a tool exists."""
        return self.registry.exists(tool_name)

    def list_domains(self):
        """Return domains when supported."""
        if hasattr(self.registry, "list_domains"):
            return self.registry.list_domains()

        return []

    def list_by_domain(self, domain):
        """Return tools by domain when supported."""
        if hasattr(self.registry, "list_by_domain"):
            return self.registry.list_by_domain(domain)

        return [tool for tool in self.list() if tool.metadata.domain == domain]
