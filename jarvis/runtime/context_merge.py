from dataclasses import dataclass
from enum import Enum


class ContextValueSource(str, Enum):
    """Stable precedence labels for runtime context diagnostics."""

    EXPLICIT = "explicit"
    CURRENT_TURN = "current_turn"
    CONVERSATION = "conversation_context"
    USER_PREFERENCE = "user_preference"
    CONFIG_DEFAULT = "config_default"
    MISSING = "missing"


@dataclass(frozen=True)
class MergedContextValue:
    value: object = None
    source: ContextValueSource = ContextValueSource.MISSING


def merge_context_value(
    *,
    explicit=None,
    current_turn=None,
    conversation=None,
    user_preference=None,
    config_default=None,
):
    """Resolve one slot with explicit data always winning over retained context."""
    candidates = (
        (ContextValueSource.EXPLICIT, explicit),
        (ContextValueSource.CURRENT_TURN, current_turn),
        (ContextValueSource.CONVERSATION, conversation),
        (ContextValueSource.USER_PREFERENCE, user_preference),
        (ContextValueSource.CONFIG_DEFAULT, config_default),
    )
    for source, value in candidates:
        if value is not None and str(value).strip() != "":
            return MergedContextValue(value=value, source=source)
    return MergedContextValue()
