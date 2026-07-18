"""Google OAuth foundation."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from jarvis.providers.google.config import GoogleProviderConfig, validate_allowed_scopes
from jarvis.providers.google.credentials import save_token_json
from jarvis.providers.google.errors import AUTH_REFRESH_FAILED, AUTH_REQUIRED, SCOPE_INSUFFICIENT, GoogleProviderError


class GoogleAuthStatus(str, Enum):
    """Structured Google authentication state."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTHENTICATED = "AUTHENTICATED"
    EXPIRED_REFRESHABLE = "EXPIRED_REFRESHABLE"
    EXPIRED_INVALID = "EXPIRED_INVALID"
    SCOPE_INSUFFICIENT = "SCOPE_INSUFFICIENT"


@dataclass(frozen=True)
class GoogleAuthState:
    """Safe Google auth state."""

    status: GoogleAuthStatus
    scopes: tuple[str, ...] = field(default_factory=tuple)
    credentials_path: str = ""
    message: str = ""

    @property
    def authenticated(self):
        """Return whether credentials can be used now."""
        return self.status == GoogleAuthStatus.AUTHENTICATED


class GoogleAuthManager:
    """Load, refresh, and report Google OAuth credentials."""

    def __init__(self, config=None, credentials=None):
        """Create auth manager with optional test-injected credentials."""
        self.config = config or GoogleProviderConfig()
        self._credentials = credentials

    def authorize(self):
        """Start installed-app authorization when Google libraries are installed."""
        unsupported = validate_allowed_scopes(self.config.scopes)
        if unsupported:
            raise GoogleProviderError(SCOPE_INSUFFICIENT, f"Unsupported scopes: {', '.join(unsupported)}")

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except Exception as error:
            raise GoogleProviderError(AUTH_REQUIRED, "Google OAuth library is not installed.", cause=error) from error

        if not Path(self.config.client_secret_path).exists():
            raise GoogleProviderError(AUTH_REQUIRED, "Google client secret file was not found.")

        flow = InstalledAppFlow.from_client_secrets_file(self.config.client_secret_path, list(self.config.scopes))
        credentials = flow.run_local_server(port=0)
        self._credentials = credentials
        self.save_credentials(credentials)
        return credentials

    def load_credentials(self):
        """Load credentials from disk or return the injected credentials."""
        if self._credentials is not None:
            return self._credentials

        if not Path(self.config.credentials_path).exists():
            return None

        try:
            from google.oauth2.credentials import Credentials
        except Exception as error:
            raise GoogleProviderError(AUTH_REQUIRED, "Google auth library is not installed.", cause=error) from error

        credentials = Credentials.from_authorized_user_file(self.config.credentials_path, list(self.config.scopes))
        self._credentials = credentials
        return credentials

    def save_credentials(self, credentials=None):
        """Persist credentials in authorized-user JSON format."""
        credentials = credentials or self._credentials

        if credentials is None:
            return None

        if str(self.config.credentials_path or "").strip() == "":
            return None

        if hasattr(credentials, "to_json"):
            import json

            return save_token_json(self.config.credentials_path, json.loads(credentials.to_json()))

        if isinstance(credentials, dict):
            return save_token_json(self.config.credentials_path, credentials)

        return None

    def refresh_credentials(self):
        """Refresh expired credentials if possible."""
        credentials = self.load_credentials()

        if credentials is None:
            raise GoogleProviderError(AUTH_REQUIRED)

        if not getattr(credentials, "expired", False):
            return credentials

        if not getattr(credentials, "refresh_token", ""):
            raise GoogleProviderError(AUTH_REFRESH_FAILED)

        try:
            try:
                from google.auth.transport.requests import Request

                request = Request()
            except Exception:
                request = None

            credentials.refresh(request)
            self.save_credentials(credentials)
            return credentials
        except Exception as error:
            raise GoogleProviderError(AUTH_REFRESH_FAILED, cause=error) from error

    def revoke_credentials(self):
        """Forget loaded credentials and remove the token file."""
        self._credentials = None
        path = Path(self.config.credentials_path)

        if path.exists():
            path.unlink()

        return True

    def get_scopes(self):
        """Return configured scopes."""
        return tuple(self.config.scopes or ())

    def get_auth_status(self):
        """Return structured auth status."""
        unsupported = validate_allowed_scopes(self.config.scopes)
        if unsupported:
            return GoogleAuthState(
                status=GoogleAuthStatus.SCOPE_INSUFFICIENT,
                scopes=tuple(self.config.scopes),
                credentials_path=self.config.credentials_path,
                message="Scope exceeds Sprint 17.0 allowlist.",
            )

        try:
            credentials = self.load_credentials()
        except GoogleProviderError as error:
            return GoogleAuthState(GoogleAuthStatus.NOT_CONFIGURED, tuple(self.config.scopes), self.config.credentials_path, error.safe_message)

        if credentials is None:
            return GoogleAuthState(GoogleAuthStatus.AUTH_REQUIRED, tuple(self.config.scopes), self.config.credentials_path)

        credential_scopes = tuple(getattr(credentials, "scopes", None) or self.config.scopes or ())
        missing = set(self.config.scopes or ()) - set(credential_scopes)
        if missing:
            return GoogleAuthState(GoogleAuthStatus.SCOPE_INSUFFICIENT, credential_scopes, self.config.credentials_path)

        if getattr(credentials, "valid", False):
            return GoogleAuthState(GoogleAuthStatus.AUTHENTICATED, credential_scopes, self.config.credentials_path)

        if getattr(credentials, "expired", False) and getattr(credentials, "refresh_token", ""):
            return GoogleAuthState(GoogleAuthStatus.EXPIRED_REFRESHABLE, credential_scopes, self.config.credentials_path)

        return GoogleAuthState(GoogleAuthStatus.EXPIRED_INVALID, credential_scopes, self.config.credentials_path)

    def is_authenticated(self):
        """Return whether current credentials are authenticated."""
        return self.get_auth_status().authenticated
