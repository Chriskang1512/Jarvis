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
        self._cached_credentials = None
        self._client_cache = {}

    def calendar_readonly_client(self):
        """Return Google Calendar API service client."""
        return self.calendar_client()

    def calendar_client(self):
        """Return Google Calendar API service client."""
        if "calendar" in self._client_cache:
            return self._client_cache["calendar"]

        credentials = self._usable_credentials()

        try:
            from googleapiclient.discovery import build
        except Exception as error:
            raise GoogleProviderError(AUTH_REQUIRED, "Google API client library is not installed.", cause=error) from error

        self._client_cache["calendar"] = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        return self._client_cache["calendar"]

    def people_client(self):
        """Return Google People API service client."""
        if "people" in self._client_cache:
            return self._client_cache["people"]

        credentials = self._usable_credentials()

        try:
            from googleapiclient.discovery import build
        except Exception as error:
            raise GoogleProviderError(AUTH_REQUIRED, "Google API client library is not installed.", cause=error) from error

        self._client_cache["people"] = build("people", "v1", credentials=credentials, cache_discovery=False)
        return self._client_cache["people"]

    def gmail_client(self):
        """Return Google Gmail API service client."""
        if "gmail" in self._client_cache:
            return self._client_cache["gmail"]

        credentials = self._usable_credentials()

        try:
            from googleapiclient.discovery import build
        except Exception as error:
            raise GoogleProviderError(AUTH_REQUIRED, "Google API client library is not installed.", cause=error) from error

        self._client_cache["gmail"] = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        return self._client_cache["gmail"]

    def _usable_credentials(self):
        """Return authenticated credentials or raise a safe error."""
        if self._cached_credentials is not None:
            return self._cached_credentials

        state = self.auth_manager.get_auth_status()
        trace_event("google_auth.status", status=state.status.value, scopes=len(state.scopes or ()))

        if state.status == GoogleAuthStatus.AUTHENTICATED:
            self._cached_credentials = self.auth_manager.load_credentials()
            return self._cached_credentials

        if state.status == GoogleAuthStatus.EXPIRED_REFRESHABLE:
            try:
                self._cached_credentials = self.auth_manager.refresh_credentials()
                return self._cached_credentials
            except GoogleProviderError:
                raise
            except Exception as error:
                raise GoogleProviderError(AUTH_REFRESH_FAILED, cause=error) from error

        if state.status == GoogleAuthStatus.SCOPE_INSUFFICIENT:
            raise GoogleProviderError(SCOPE_INSUFFICIENT)

        raise GoogleProviderError(AUTH_REQUIRED)
