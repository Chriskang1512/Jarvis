def extract_text(input_data):
    """Return the free-form user idea from tool input."""
    return str(input_data.get("text", "")).strip()


def default_idea(text):
    """Return a usable creative idea."""
    if text == "":
        return "starting again after a hard season"

    return text


def detect_language(text):
    """Return the likely language for generated creative assets."""
    if any("가" <= char <= "힣" for char in text):
        return "ko"

    return "en"


def title_case_slug(text):
    """Create a compact English-like title seed."""
    words = [
        word.strip(".,!?")
        for word in text.replace("_", " ").split()
        if word.strip(".,!?") != ""
    ]

    if len(words) == 0:
        return "Start Again"

    return " ".join(word.capitalize() for word in words[:6])


def project_id_from_idea(idea, fallback="creator_project"):
    """Create a stable project id from a creative idea."""
    words = [
        word.strip(".,!?").lower()
        for word in idea.replace("_", " ").split()
        if word.strip(".,!?") != ""
    ]

    ascii_words = [
        "".join(char for char in word if char.isalnum())
        for word in words
        if word.isascii()
    ]
    ascii_words = [word for word in ascii_words if word != ""]

    if len(ascii_words) == 0:
        return fallback

    return "_".join(ascii_words[:6])


def asset_header(idea, asset, subdomain="song", project=None):
    """Return standard Creator asset contract fields."""
    return {
        "project": project or project_id_from_idea(idea),
        "subdomain": subdomain,
        "asset": asset,
    }
