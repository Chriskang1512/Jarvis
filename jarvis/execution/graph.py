from jarvis.execution.contracts import ExecutionInputData
from jarvis.tools import ToolRequest


class MetadataCapabilityRouter:
    """Route capability-level intent nodes to tools using tool metadata."""

    def __init__(self, tool_registry):
        """Create a router from a ToolRegistry-like object."""
        self.tool_registry = tool_registry

    def route(self, node, context=None):
        """Return a ToolRequest for a capability node."""
        node_dict = node.to_dict() if hasattr(node, "to_dict") else node
        capability = node_dict.get("capability", "")
        intent = node_dict.get("intent", "")
        candidates = []

        for tool in self.tool_registry.list():
            metadata = tool.metadata

            if metadata.deprecated or metadata.capability != capability:
                continue

            score = score_tool_for_intent(metadata, intent)

            if score <= 0:
                continue

            candidates.append((score, metadata.priority, metadata.name))

        if len(candidates) == 0:
            raise ValueError(f"No tool route for capability '{capability}' intent '{intent}'.")

        candidates.sort(reverse=True)
        return ToolRequest(
            tool_name=candidates[0][2],
            input_data=build_input_data(node_dict, context),
        )


def build_input_data(node_dict, context):
    """Build tool input with resolved execution context."""
    snapshot = None
    previous_results = []

    if context is not None:
        snapshot = context.snapshot()
        previous_results = [
            value.get("result")
            for value in snapshot["values"].values()
        ]

    return ExecutionInputData(
        user_input=node_dict.get("input", ""),
        previous_results=previous_results,
        execution_snapshot=snapshot,
    ).to_dict()


def score_tool_for_intent(metadata, intent):
    """Score one tool against a capability-level intent."""
    normalized_intent = normalize(intent)
    supported_intents = [normalize(value) for value in metadata.supported_intents]
    aliases = [normalize(value) for value in metadata.aliases]
    examples = [normalize(value) for value in metadata.examples]

    if normalized_intent in supported_intents:
        return 1.0

    if normalized_intent in aliases:
        return 0.95

    if normalized_intent in examples:
        return 0.9

    return 0.0


def normalize(text):
    """Normalize text for metadata matching."""
    return " ".join(str(text).lower().strip().split())
