import re
from dataclasses import dataclass, field
from typing import Protocol

from jarvis.abilities.integration.n8n.parser import is_integration_workflow_request


ARITHMETIC_PATTERN = re.compile(r"^[\d\s().+\-*/%]+$")


@dataclass(frozen=True)
class ToolRoute:
    """Concrete tool route selected for one intent."""

    tool_name: str
    input_data: dict = field(default_factory=dict)
    tool: object = None


class ToolRouter(Protocol):
    """Common router contract for Brain, filesystem, cloud, and plugin routers."""

    def resolve(self, intent):
        """Return a ToolRoute for one intent, or None."""
        ...


class RegistryToolRouter:
    """Resolve intents to tools using registry metadata."""

    def __init__(self, registry):
        """Create a registry-backed router."""
        self.registry = registry

    def resolve(self, intent):
        """Return a route for one intent without exposing registry details."""
        if intent is None or getattr(intent, "tool_name", "") == "":
            return None

        tool = self.registry.get(intent.tool_name)

        if tool is None:
            return None

        return ToolRoute(
            tool_name=tool.metadata.name,
            input_data=dict(intent.parameters),
            tool=tool,
        )


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

    if getattr(metadata, "name", "") == "reminder" and is_relative_reminder_request(normalized_text):
        return 0.95

    if getattr(metadata, "name", "") == "integration_n8n" and (
        is_integration_health_request(normalized_text) or is_integration_workflow_request(normalized_text)
    ):
        return 0.95

    if contains_alias(normalized_text, normalized_aliases):
        return 0.85

    return 0.0


def is_relative_reminder_request(normalized_text):
    """Return whether text is a relative reminder request without explicit alarm noun."""
    text = str(normalized_text or "")

    if not re.search(r"\d+\s*(분|시간)\s*(뒤에|뒤|후에|후)", text):
        return False

    return bool(re.search(r"(알려\s*줘|알려줘|해\s*줘|해줘|알림|알람|등록해)", text))


def is_integration_health_request(normalized_text):
    """Return whether text asks for n8n or integration bridge health."""
    text = str(normalized_text or "").lower()
    n8n_aliases = ["n8n", "맨발은", "엔에잇엔", "엔팔엔"]
    health_tokens = ["health", "상태", "헬스", "연결"]

    if any(alias in text for alias in n8n_aliases) and any(token in text for token in health_tokens):
        return True

    if is_loose_integration_health_match(text):
        return True

    health_phrases = [
        "외부 자동화 연결 상태 확인해줘",
        "외부 자동화 연결 상태 확인해 줘",
        "자동화 브리지 상태 확인해줘",
        "자동화 브리지 상태 확인해 줘",
        "연동 상태 확인해줘",
        "연동 상태 확인해 줘",
        "외부 서비스 연결 상태 확인해줘",
        "외부 서비스 연결 상태 확인해 줘",
    ]
    return any(phrase in text for phrase in health_phrases)


def is_loose_integration_health_match(text):
    """Return whether text is a natural Korean integration-health request."""
    normalized = str(text or "").lower()
    subjects = [
        "\uc678\ubd80 \uc790\ub3d9\ud654",
        "\uc790\ub3d9\ud654 \ube0c\ub9ac\uc9c0",
        "\ube0c\ub9ac\uc9c0",
        "\uc5f0\ub3d9",
        "\uc678\ubd80 \uc11c\ube44\uc2a4",
        "\uc11c\ube44\uc2a4",
    ]
    action_tokens = ["\uc5f0\uacb0", "\uc0c1\ud0dc", "\ud655\uc778", "health"]

    return any(subject in normalized for subject in subjects) and any(token in normalized for token in action_tokens)


def contains_alias(normalized_text, normalized_aliases):
    """Return whether a route alias appears as a standalone intent keyword."""
    tokens = [token.strip(".,?!:;。！？") for token in normalized_text.split()]

    for alias in normalized_aliases:
        if alias == "":
            continue

        if normalized_text == alias:
            return True

        if alias in tokens:
            return True

        if f" {alias} " in f" {normalized_text} ":
            return True

    return False


def build_input_data(metadata, text, matched_prefix):
    """Build tool input using metadata-selected input handling."""
    integration_input = build_integration_input_data(metadata, text, matched_prefix)

    if integration_input is not None:
        return integration_input

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


def build_integration_input_data(metadata, text, matched_prefix):
    """Build stable Integration workflow input for prefix-routed commands."""
    if getattr(metadata, "name", "") != "integration_n8n":
        return None

    normalized_prefix = normalize_text(matched_prefix)

    if normalized_prefix in ("system.echo", "system echo", "echo", "에코"):
        message = str(text or "")[len(matched_prefix):].strip().rstrip("?")
        message = strip_echo_command_suffix(message)
        return {
            "workflow_key": "system.echo",
            "action": "system.echo",
            "payload": {"message": message},
            "raw_text": str(text or ""),
        }

    if normalized_prefix in ("system.health", "system health"):
        return {
            "workflow_key": "system.health",
            "action": "system.health",
            "payload": {},
            "raw_text": str(text or ""),
        }

    return None


def strip_echo_command_suffix(text):
    """Remove common spoken send suffixes from an echo payload."""
    value = str(text or "").strip()
    suffixes = [
        "보내 줘",
        "보내줘",
        "전송해 줘",
        "전송해줘",
        "보여 줘",
        "보여줘",
    ]

    for suffix in suffixes:
        if value.endswith(suffix):
            value = value[: -len(suffix)].strip()
            break

    if len(value) > 1 and value[-1] in ("을", "를"):
        value = value[:-1].strip()

    return value


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
