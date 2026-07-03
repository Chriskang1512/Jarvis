from jarvis.tools.safe_tools import (
    CalculatorTool,
    DiagnosticsSummaryTool,
    MemoryReadTool,
    TimeTool,
)


class ToolRegistry:
    """Store and look up available tools."""

    def __init__(self):
        """Create an empty tool registry."""
        self.tools = {}

    def register(self, tool):
        """Register one tool by metadata name."""
        self.tools[tool.metadata.name] = tool

    def get(self, tool_name):
        """Return one tool by name, or None when unavailable."""
        return self.tools.get(tool_name)

    def list(self):
        """Return all registered tools sorted by name."""
        return [self.tools[name] for name in sorted(self.tools)]

    def exists(self, tool_name):
        """Return whether a tool is registered."""
        return tool_name in self.tools


def create_default_tool_registry(diagnostics_collector=None, memory_service=None):
    """Create the default registry with safe built-in tools."""
    registry = ToolRegistry()
    registry.register(TimeTool())
    registry.register(CalculatorTool())
    registry.register(DiagnosticsSummaryTool(diagnostics_collector=diagnostics_collector))
    registry.register(MemoryReadTool(memory_service=memory_service))
    return registry
