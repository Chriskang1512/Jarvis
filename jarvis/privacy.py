"""Privacy helpers for logs and retained local artifacts."""

import re


PHONE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:"
    r"(?:(?:\+?82[\s().-]?|0)1[016789][\s().-]?\d{3,4}[\s().-]?\d{4})"
    r"|"
    r"(?:0\d{1,2}[\s().-]?\d{3,4}[\s().-]?\d{4})"
    r")"
    r"(?!\d)"
)
EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r"(?![A-Za-z0-9._%+-])"
)


def redact_sensitive_text(value):
    """Redact phone numbers and email addresses for logs."""
    text = str(value or "")
    text = EMAIL_PATTERN.sub(redact_email_match, text)
    text = PHONE_PATTERN.sub(redact_phone_match, text)
    return text


def contains_sensitive_text(value):
    """Return whether text contains obvious contact PII."""
    text = str(value or "")
    mail_preview = "내용은 '" in text and ("메일을 보낼까요" in text or "답장을 보낼까요" in text)
    return bool(EMAIL_PATTERN.search(text) or PHONE_PATTERN.search(text) or mail_preview)


def redact_email_match(match):
    """Return a masked email address."""
    value = match.group(0)
    local, _, domain = value.partition("@")

    if local == "":
        return "***@" + domain

    return f"{local[0]}***@{domain}"


def redact_phone_match(match):
    """Return a masked phone number while preserving the last four digits."""
    value = match.group(0)
    digits = re.sub(r"\D", "", value)

    if len(digits) < 8:
        return value

    if value.strip().startswith("+"):
        return f"+{digits[:2]}-****-{digits[-4:]}"

    return f"{digits[:3]}-****-{digits[-4:]}"
