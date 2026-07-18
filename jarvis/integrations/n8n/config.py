import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class N8nConfig:
    """Configuration for the n8n bridge provider."""

    provider: str = "mock"
    base_url: str = ""
    api_token: str = ""
    webhook_secret: str = ""
    request_timeout: int = 15
    bridge_enabled: bool = False
    healthcheck_on_startup: bool = False
    max_payload_bytes: int = 65536


def load_n8n_config():
    """Load n8n bridge settings from environment or .env."""
    return N8nConfig(
        provider=read_env("JARVIS_INTEGRATION_PROVIDER", "mock").lower(),
        base_url=read_env("N8N_BASE_URL", ""),
        api_token=read_env("N8N_API_TOKEN", ""),
        webhook_secret=read_env("N8N_WEBHOOK_SECRET", ""),
        request_timeout=read_int_env("N8N_REQUEST_TIMEOUT", 15),
        bridge_enabled=read_bool_env("N8N_BRIDGE_ENABLED", False),
        healthcheck_on_startup=read_bool_env("N8N_HEALTHCHECK_ON_STARTUP", False),
    )


def read_int_env(key, default):
    """Read an integer environment value."""
    try:
        return int(read_env(key, str(default)))
    except ValueError:
        return default


def read_bool_env(key, default):
    """Read a boolean environment value."""
    value = read_env(key, "")

    if value == "":
        return default

    return value.lower() in ["1", "true", "yes", "on"]


def read_env(key, default=""):
    """Read a value from process env or local .env."""
    value = os.environ.get(key, "")

    if value != "":
        return value

    env_path = Path(".env")

    if not env_path.exists():
        return default

    with env_path.open("r", encoding="utf-8") as file:
        for line in file:
            env_key, env_value = parse_env_line(line)

            if env_key == key:
                return env_value

    return default


def parse_env_line(line):
    """Parse a KEY=VALUE .env line."""
    stripped = str(line or "").strip()

    if stripped == "" or stripped.startswith("#") or "=" not in stripped:
        return "", ""

    key, value = stripped.split("=", 1)
    return key.strip(), clean_env_value(value)


def clean_env_value(value):
    """Remove simple quotes from an env value."""
    cleaned = str(value or "").strip()

    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ["'", '"']:
        return cleaned[1:-1]

    return cleaned
