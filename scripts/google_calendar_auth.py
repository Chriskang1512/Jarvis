"""Run Google Calendar read-only OAuth for Jarvis."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.config.loader import ConfigurationLoader
from jarvis.providers.google.auth import GoogleAuthManager
from jarvis.providers.google.config import GOOGLE_CALENDAR_READONLY_SCOPE, GoogleProviderConfig
from jarvis.providers.google.errors import GoogleProviderError


def main():
    """Authorize Google Calendar read-only access."""
    config = ConfigurationLoader().load()
    google_config = GoogleProviderConfig(
        credentials_path=config.calendar.google_credentials_path,
        client_secret_path=config.calendar.google_client_secret_path,
        scopes=(GOOGLE_CALENDAR_READONLY_SCOPE,),
        timezone=config.calendar.timezone,
    )
    manager = GoogleAuthManager(google_config)

    try:
        manager.authorize()
    except GoogleProviderError as error:
        print(error.safe_message)
        return 1

    status = manager.get_auth_status()
    print(f"Google Calendar auth status: {status.status.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
