"""Explicit privacy boundary before execution memory persistence."""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass


class MemoryRedactor:
    SENSITIVE_KEYS = {
        "access_token",
        "accesstoken",
        "refresh_token",
        "refreshtoken",
        "password",
        "oauth_secret",
        "oauthsecret",
        "client_secret",
        "mail_body",
        "body",
        "attachment",
        "attachments",
        "contact",
        "contacts",
        "tool_input",
        "tool_output",
        "raw_input",
        "raw_output",
        "approval_audio",
        "transcript",
        "original_input",
    }

    def redact_allowlisted(self, value, allowed_keys):
        """Copy only explicitly approved fields, then apply value redaction."""
        if not isinstance(value, dict):
            raise TypeError("Allowlisted memory metadata must be a dictionary.")
        allowed = {str(key) for key in allowed_keys}
        return self.redact(
            {
                str(key): item
                for key, item in value.items()
                if str(key) in allowed
            }
        )

    def redact(self, value):
        if is_dataclass(value):
            value = asdict(value)
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
                if normalized in {
                    re.sub(r"[^a-z0-9]", "", name)
                    for name in self.SENSITIVE_KEYS
                }:
                    result[str(key)] = "[REDACTED]"
                else:
                    result[str(key)] = self.redact(item)
            return result
        if isinstance(value, (list, tuple)):
            return [self.redact(item) for item in value]
        if isinstance(value, str):
            value = re.sub(
                r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
                "[REDACTED_EMAIL]",
                value,
            )
            value = re.sub(
                r"(?<!\d)(?:\+?\d[\d -]{7,}\d)(?!\d)",
                "[REDACTED_PHONE]",
                value,
            )
        return value
