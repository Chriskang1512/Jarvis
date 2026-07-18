"""Google provider foundation."""

from jarvis.providers.google.auth import GoogleAuthManager, GoogleAuthStatus
from jarvis.providers.google.config import GOOGLE_CALENDAR_READONLY_SCOPE, GoogleProviderConfig
from jarvis.providers.google.errors import GoogleProviderError

__all__ = [
    "GOOGLE_CALENDAR_READONLY_SCOPE",
    "GoogleAuthManager",
    "GoogleAuthStatus",
    "GoogleProviderConfig",
    "GoogleProviderError",
]
