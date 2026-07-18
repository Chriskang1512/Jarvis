"""Google API client factory."""

from jarvis.providers.google.auth import GoogleAuthManager, GoogleAuthStatus
from jarvis.providers.google.config import GoogleProviderConfig
from jarvis.providers.google.errors import AUTH_REQUIRED, AUTH_REFRESH_FAILED, SCOPE_INSUFFICIENT, GoogleProviderError
from jarvis.debug_trace import trace_event


class GoogleClientFactory:
    """Create Google service clients from managed credentials."""

    def __init__(self, auth_manager=None, config=None):
        """Create factory."""
        self.config = config or GoogleProviderConfig()
        self.auth_manager = auth_manager or GoogleAuthManager(self.config)

    def calendar_readonly_client(self):
        """Return Google Calendar API service client."""
        credentials = self._usable_credentials()

        try:
            from googleapiclient.discovery import build
        except Exception as error:
            raise GoogleProviderError(AUTH_REQUIRED, "Google API client library is not installed.", cause=error) from error

        return build("calendar", "v3", credentials=credentials, cache_discovery=False)

    def _usable_credentials(self):
        """Return authenticated credentials or raise a safe error."""
        state = self.auth_manager.get_auth_status()
        trace_event("google_auth.status", status=state.status.value, scopes=len(state.scopes or ()))

        if state.status == GoogleAuthStatus.AUTHENTICATED:
            return self.auth_manager.load_credentials()

        if state.status == GoogleAuthStatus.EXPIRED_REFRESHABLE:
            try:
                return self.auth_manager.refresh_credentials()
            except GoogleProviderError:
                raise
            except Exception as error:
                raise GoogleProviderError(AUTH_REFRESH_FAILED, cause=error) from error

        if state.status == GoogleAuthStatus.SCOPE_INSUFFICIENT:
            raise GoogleProviderError(SCOPE_INSUFFICIENT)

        raise GoogleProviderError(AUTH_REQUIRED)
