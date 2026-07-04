def text_input(input_data):
    """Return normalized text from tool input."""
    if not isinstance(input_data, dict):
        return ""

    return str(input_data.get("text", "")).strip()


def default_topic(text, fallback):
    """Return text or a fallback topic."""
    if text == "":
        return fallback

    return text


def split_items(text):
    """Split a loose user request into reusable item fragments."""
    separators = [",", "\n", "/", "|"]
    normalized = text

    for separator in separators:
        normalized = normalized.replace(separator, ";")

    items = [item.strip(" -") for item in normalized.split(";") if item.strip(" -") != ""]
    if len(items) == 0 and text.strip() != "":
        items = [text.strip()]

    return items


def contains_any(text, keywords):
    """Return whether text contains any keyword."""
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)
