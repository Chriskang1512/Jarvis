"""Google credential storage helpers."""

import json
from pathlib import Path


SENSITIVE_KEYS = {"access_token", "refresh_token", "token", "client_secret", "authorization", "code"}


def load_token_json(path):
    """Load a Google token JSON file."""
    token_path = Path(path)

    if not token_path.exists():
        return None

    with token_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_token_json(path, data):
    """Save a Google token JSON file."""
    token_path = Path(path)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    with token_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)

    return token_path


def redact_mapping(value):
    """Return a redacted copy of a mapping for safe logging."""
    result = {}

    for key, item in dict(value or {}).items():
        if str(key).lower() in SENSITIVE_KEYS:
            result[key] = "[REDACTED]"
        else:
            result[key] = item

    return result
