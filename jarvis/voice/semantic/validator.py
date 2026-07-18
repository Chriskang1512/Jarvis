"""Validation helpers for semantic transcript corrections."""


def is_safe_semantic_result(result):
    """Return whether a semantic result is safe to pass to intent parsing."""
    if result is None:
        return False

    if getattr(result, "requires_clarification", False):
        return False

    semantic_text = str(getattr(result, "semantic_text", "") or "").strip()
    return semantic_text != ""
