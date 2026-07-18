from jarvis.permissions import PermissionLayer
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolRequest
from jarvis.tools.router import select_candidate


class BrainToolRouter:
    """Choose safe tools from registry metadata."""

    def __init__(self, min_confidence=0.75):
        """Create a metadata-driven tool router."""
        self.min_confidence = min_confidence

    def plan(self, message, registry=None, permission_layer=None):
        """Return a ToolRequest when registry metadata clearly matches the message."""
        text = message.strip()

        if text == "" or registry is None:
            return None

        permission_layer = permission_layer or PermissionLayer()
        candidates = []

        for tool in registry.list():
            if tool.metadata.deprecated:
                continue

            if not is_safe_tool(tool):
                continue

            if not permission_layer.evaluate(tool).allowed:
                continue

            candidate = select_candidate(tool, text)

            if candidate is not None:
                candidates.append(candidate)

        if len(candidates) == 0:
            return None

        candidates.sort(
            key=lambda candidate: (
                candidate["confidence"],
                candidate["tool"].metadata.priority,
            ),
            reverse=True,
        )
        selected = candidates[0]

        if selected["confidence"] < self.min_confidence:
            return None

        return ToolRequest(
            tool_name=selected["tool"].metadata.name,
            input_data=selected["input_data"],
        )


def is_safe_tool(tool):
    """Return whether a tool is safe enough for automatic Brain routing."""
    level = tool.metadata.permission_level

    if isinstance(level, PermissionLevel):
        return tool.metadata.safe and level == PermissionLevel.SAFE

    return tool.metadata.safe and str(level).lower() == PermissionLevel.SAFE.value
