"""Google provider foundation."""

from jarvis.providers.google.auth import GoogleAuthManager, GoogleAuthStatus
from jarvis.providers.google.config import (
    GOOGLE_CALENDAR_READONLY_SCOPE,
    GOOGLE_CALENDAR_SCOPE,
    GOOGLE_CONTACTS_READONLY_SCOPE,
    GOOGLE_CONTACTS_SCOPE,
    GOOGLE_GMAIL_READONLY_SCOPE,
    GoogleProviderConfig,
)
from jarvis.providers.google.context import GoogleProviderContext
from jarvis.providers.google.credentials import GoogleCredentialStore
from jarvis.providers.google.error_mapper import GoogleErrorMapper
from jarvis.providers.google.errors import GoogleProviderError
from jarvis.providers.google.metadata import GoogleProviderMetadata
from jarvis.providers.google.request_executor import GoogleRequestExecutor

__all__ = [
    "GOOGLE_CALENDAR_READONLY_SCOPE",
    "GOOGLE_CALENDAR_SCOPE",
    "GOOGLE_CONTACTS_READONLY_SCOPE",
    "GOOGLE_CONTACTS_SCOPE",
    "GOOGLE_GMAIL_READONLY_SCOPE",
    "GoogleAuthManager",
    "GoogleAuthStatus",
    "GoogleCredentialStore",
    "GoogleErrorMapper",
    "GoogleProviderContext",
    "GoogleProviderConfig",
    "GoogleProviderError",
    "GoogleProviderMetadata",
    "GoogleRequestExecutor",
]
