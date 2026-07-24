"""Google provider configuration."""

from dataclasses import dataclass


GOOGLE_CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
GOOGLE_CONTACTS_READONLY_SCOPE = "https://www.googleapis.com/auth/contacts.readonly"
GOOGLE_CONTACTS_SCOPE = "https://www.googleapis.com/auth/contacts"
GOOGLE_GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
ALLOWED_SPRINT_17_SCOPES = frozenset({
    GOOGLE_CALENDAR_READONLY_SCOPE,
    GOOGLE_CALENDAR_SCOPE,
    GOOGLE_CONTACTS_READONLY_SCOPE,
    GOOGLE_CONTACTS_SCOPE,
    GOOGLE_GMAIL_READONLY_SCOPE,
    GOOGLE_GMAIL_SEND_SCOPE,
})


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


def missing_required_scopes(required_scopes, granted_scopes):
    """Return required scopes not satisfied by granted scopes."""
    granted = set(granted_scopes or ())
    missing = []

    for scope in required_scopes or ():
        if scope in granted:
            continue
        if scope == GOOGLE_CALENDAR_READONLY_SCOPE and GOOGLE_CALENDAR_SCOPE in granted:
            continue
        if scope == GOOGLE_CONTACTS_READONLY_SCOPE and GOOGLE_CONTACTS_SCOPE in granted:
            continue
        missing.append(scope)

    return tuple(missing)
