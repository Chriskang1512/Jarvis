"""Google provider configuration."""

from dataclasses import dataclass


GOOGLE_CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
ALLOWED_SPRINT_17_SCOPES = frozenset({GOOGLE_CALENDAR_READONLY_SCOPE})


@dataclass(frozen=True)
class GoogleProviderConfig:
    """Google provider config shared by auth and clients."""

    credentials_path: str = "data/credentials/google_token.json"
    client_secret_path: str = "client_secret.json"
    scopes: tuple[str, ...] = (GOOGLE_CALENDAR_READONLY_SCOPE,)
    timezone: str = "Asia/Seoul"
    calendar_id: str = "primary"
    timeout_seconds: float = 8.0


def validate_allowed_scopes(scopes):
    """Return unsupported scopes for the current sprint."""
    requested = set(scopes or ())
    return tuple(sorted(requested - ALLOWED_SPRINT_17_SCOPES))
