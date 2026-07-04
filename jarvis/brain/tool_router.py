import re

from jarvis.permissions import PermissionLayer
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolRequest


ARITHMETIC_PATTERN = re.compile(r"^[\d\s().+\-*/%]+$")


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


def select_candidate(tool, text):
    """Return a scored route candidate for one tool and message."""
    metadata = tool.metadata
    normalized_text = normalize_text(text)
    matched_prefix = find_matched_prefix(text, metadata.input_prefixes)
    confidence = score_metadata_match(metadata, normalized_text, matched_prefix)

    if metadata.input_mode == "arithmetic_expression" and is_arithmetic_expression(text):
        confidence = max(confidence, metadata.route_confidence)

    if confidence < metadata.route_confidence:
        return None

    input_data = build_input_data(metadata, text, matched_prefix)

    if input_data is None:
        return None

    return {
        "tool": tool,
        "confidence": confidence,
        "input_data": input_data,
    }


def score_metadata_match(metadata, normalized_text, matched_prefix):
    """Score one message against metadata-provided aliases and intents."""
    normalized_aliases = [normalize_text(value) for value in metadata.aliases]
    normalized_intents = [normalize_text(value) for value in metadata.supported_intents]
    normalized_examples = [normalize_text(value) for value in metadata.examples]

    if normalized_text in normalized_aliases or normalized_text in normalized_intents:
        return 1.0

    if normalized_text in normalized_examples:
        return 0.98

    if matched_prefix != "":
        return 0.95

    return 0.0


def build_input_data(metadata, text, matched_prefix):
    """Build tool input using metadata-selected input handling."""
    if metadata.input_mode == "none":
        return {}

    value = text

    if matched_prefix != "":
        value = text[len(matched_prefix):]

    value = value.strip().rstrip("?")

    if value == "" and not metadata.allow_empty_input:
        return None

    if metadata.input_mode == "arithmetic_expression":
        if not is_arithmetic_expression(value):
            return None

        return {"expression": value}

    if metadata.input_mode == "query":
        return {"key": value}

    return {"text": value}


def find_matched_prefix(text, prefixes):
    """Find a metadata prefix at the start of a message."""
    normalized_text = normalize_text(text)

    for prefix in sorted(prefixes, key=len, reverse=True):
        normalized_prefix = normalize_text(prefix)

        if normalized_text == normalized_prefix:
            return prefix

        if normalized_text.startswith(f"{normalized_prefix} "):
            return text[: len(prefix)]

    return ""


def is_arithmetic_expression(text):
    """Return whether text is a bounded arithmetic expression."""
    expression = text.strip().rstrip("?")
    return ARITHMETIC_PATTERN.match(expression) and contains_operator(expression)


def contains_operator(expression):
    """Return whether an arithmetic expression contains an operator."""
    return any(operator in expression for operator in ["+", "-", "*", "/", "%"])


def normalize_text(text):
    """Normalize user and metadata text for routing comparison."""
    return " ".join(text.strip().lower().rstrip("?").split())
