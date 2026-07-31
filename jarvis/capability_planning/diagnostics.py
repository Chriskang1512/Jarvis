"""Privacy-safe Planner diagnostics."""

from __future__ import annotations

import hashlib
import re


EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d ().-]{7,}\d)(?!\d)")
WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:\\(?:[^\\\s]+\\)*[^\\\s]*")
UNIX_PATH = re.compile(r"(?<!\w)/(?:[^/\s]+/)*[^/\s]+")
SECRET = re.compile(
    r"(?i)\b(authorization|oauth|access[_-]?token|refresh[_-]?token|"
    r"api[_-]?key|client[_-]?secret)\b\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)
CONTENT_FIELD = re.compile(
    r"(?i)\b(title|subject|body|message|event_title|"
    r"provider_response|raw_response)\b\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^,;\n]+)"
)


class PlannerDiagnosticsSanitizer:
    @staticmethod
    def sanitize_text(value):
        text = str(value or "")
        text = SECRET.sub(
            lambda match: f"{match.group(1)}=[REDACTED_SECRET]",
            text,
        )
        text = EMAIL.sub("[REDACTED_EMAIL]", text)
        text = PHONE.sub("[REDACTED_PHONE]", text)
        text = WINDOWS_PATH.sub("[REDACTED_PATH]", text)
        text = UNIX_PATH.sub("[REDACTED_PATH]", text)
        text = CONTENT_FIELD.sub(
            lambda match: f"{match.group(1)}=[REDACTED_CONTENT]",
            text,
        )
        return text[:240]

    @staticmethod
    def input_fingerprint(value):
        text = str(value or "")
        return len(text), hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def entity_summary(context):
        return tuple(
            {
                "type": str(entity.entity_type),
                "confidence": float(entity.confidence),
            }
            for entity in context.entities
        )
