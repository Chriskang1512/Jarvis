import re


def normalize_tts_text(text):
    """Convert simple Markdown-like response text into TTS-friendly plain text."""
    normalized = str(text)
    normalized = strip_code_fences(normalized)
    normalized = strip_heading_markers(normalized)
    normalized = strip_bullet_markers(normalized)
    normalized = strip_emphasis_markers(normalized)
    normalized = strip_inline_code_markers(normalized)
    normalized = strip_link_markup(normalized)
    normalized = collapse_excess_blank_lines(normalized)
    return normalized.strip()


def strip_code_fences(text):
    """Remove fenced-code markers while keeping code text."""
    return re.sub(r"^\s*`{3,}.*$", "", text, flags=re.MULTILINE)


def strip_heading_markers(text):
    """Remove Markdown heading prefixes."""
    return re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)


def strip_bullet_markers(text):
    """Remove simple Markdown bullet prefixes."""
    return re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)


def strip_emphasis_markers(text):
    """Remove common Markdown emphasis markers."""
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
    return text


def strip_inline_code_markers(text):
    """Remove inline-code backticks."""
    return re.sub(r"`([^`]*)`", r"\1", text)


def strip_link_markup(text):
    """Convert Markdown links to readable label text."""
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)


def collapse_excess_blank_lines(text):
    """Keep paragraph breaks compact for TTS."""
    return re.sub(r"\n{3,}", "\n\n", text)
