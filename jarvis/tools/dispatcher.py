from jarvis.tools.contracts import ToolRequest, ToolResult


class ToolDispatcher:
    """Select and execute registered tools."""

    def __init__(self, registry, diagnostics_collector=None):
        """Create a dispatcher using one registry."""
        self.registry = registry
        self.diagnostics_collector = diagnostics_collector

    def execute(self, request):
        """Execute one tool request and return a structured result."""
        tool_request = normalize_request(request)
        self.log_event("tool.requested")
        tool = self.registry.get(tool_request.tool_name)

        if tool is None:
            self.log_event("tool.failed")
            return ToolResult(
                tool_name=tool_request.tool_name,
                success=False,
                error=f"Tool '{tool_request.tool_name}' is not registered.",
            )

        self.log_event("tool.selected")
        self.log_event("tool.started")

        try:
            result = tool.execute(tool_request.input_data)
        except Exception as error:
            self.log_event("tool.failed")
            return ToolResult(
                tool_name=tool_request.tool_name,
                success=False,
                error=str(error),
            )

        if result.success:
            self.log_event("tool.completed")
        else:
            self.log_event("tool.failed")

        return result

    def log_event(self, message):
        """Publish one diagnostics event when available."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.log_event(message)


def normalize_request(request):
    """Return a ToolRequest for raw names or request objects."""
    if isinstance(request, ToolRequest):
        return request

    return ToolRequest(tool_name=str(request), input_data={})
