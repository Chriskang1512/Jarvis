"""Map Gmail API payloads into Jarvis Mail messages."""

import base64
import re
from email.utils import getaddresses, parseaddr

from jarvis.abilities.native.mail.result import MailMessage


class GoogleMailMapper:
    """Convert Gmail API message resources to MailMessage."""

    def to_message(self, payload):
        """Return one normalized MailMessage."""
        data = dict(payload or {})
        headers = headers_to_dict(dict(data.get("payload") or {}).get("headers") or [])
        sender_name, sender_email = parse_sender(headers.get("from", ""))
        recipients = tuple(address for _, address in getaddresses([headers.get("to", "")]) if address)
        labels = tuple(str(label or "") for label in data.get("labelIds") or ())
        parts = collect_parts(dict(data.get("payload") or {}))
        attachment_count = sum(1 for part in parts if part.get("filename"))
        body_text = first_text_part(parts) or str(data.get("snippet") or "")

        return MailMessage(
            id=str(data.get("id") or ""),
            thread_id=str(data.get("threadId") or ""),
            sender_name=sender_name,
            sender_email=sender_email,
            subject=headers.get("subject", ""),
            snippet=clean_text(str(data.get("snippet") or "")),
            received_at=str(data.get("internalDate") or ""),
            unread="UNREAD" in labels,
            labels=labels,
            has_attachment=attachment_count > 0,
            attachment_count=attachment_count,
            body_summary=clean_text(body_text)[:500],
            to=recipients,
            rfc_message_id=headers.get("message-id", ""),
        )

    def list_to_messages(self, response):
        """Return message references from a list response."""
        data = dict(response or {})
        messages = []

        for item in data.get("messages") or []:
            if isinstance(item, dict):
                messages.append(MailMessage(id=str(item.get("id") or ""), thread_id=str(item.get("threadId") or "")))

        return tuple(messages)


def headers_to_dict(headers):
    """Return lower-case header mapping."""
    output = {}

    for header in headers or []:
        name = str(dict(header or {}).get("name") or "").lower()
        value = str(dict(header or {}).get("value") or "")
        if name:
            output[name] = value

    return output


def parse_sender(value):
    """Return display name and email from a From header."""
    name, email = parseaddr(str(value or ""))
    return clean_text(name), clean_text(email)


def collect_parts(payload):
    """Flatten Gmail message parts."""
    data = dict(payload or {})
    parts = [data]

    for child in data.get("parts") or []:
        parts.extend(collect_parts(child))

    return parts


def first_text_part(parts):
    """Return first decoded text/plain or text/html body."""
    fallback = ""

    for part in parts or []:
        mime = str(part.get("mimeType") or "")
        body = dict(part.get("body") or {})
        data = str(body.get("data") or "")

        if not data:
            continue

        decoded = decode_gmail_body(data)

        if mime == "text/plain":
            return decoded
        if mime == "text/html" and not fallback:
            fallback = strip_html(decoded)

    return fallback


def decode_gmail_body(value):
    """Decode Gmail base64url body text."""
    try:
        padded = str(value or "") + "=" * (-len(str(value or "")) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def strip_html(value):
    """Return compact text from simple HTML."""
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return clean_text(text)


def clean_text(value):
    """Collapse whitespace for speech-safe snippets."""
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
