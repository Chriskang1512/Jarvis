"""Run Google OAuth for Jarvis Gmail read/send access."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.config.loader import ConfigurationLoader
from jarvis.providers.google.auth import GoogleAuthManager
from jarvis.providers.google.config import (
    GOOGLE_CALENDAR_SCOPE,
    GOOGLE_CONTACTS_SCOPE,
    GOOGLE_GMAIL_READONLY_SCOPE,
    GOOGLE_GMAIL_SEND_SCOPE,
    GoogleProviderConfig,
)
from jarvis.providers.google.errors import GoogleProviderError


def main():
    """Authorize Calendar/Contacts plus Gmail read and send."""
    config = ConfigurationLoader().load()
    google_config = GoogleProviderConfig(
        credentials_path=config.mail.google_credentials_path,
        client_secret_path=config.mail.google_client_secret_path,
        scopes=(
            GOOGLE_CALENDAR_SCOPE,
            GOOGLE_CONTACTS_SCOPE,
            GOOGLE_GMAIL_READONLY_SCOPE,
            GOOGLE_GMAIL_SEND_SCOPE,
        ),
        timezone=config.calendar.timezone,
    )
    manager = GoogleAuthManager(google_config)

    try:
        manager.authorize()
    except GoogleProviderError as error:
        print(error.safe_message)
        return 1

    status = manager.get_auth_status()
    print(f"Google Gmail auth status: {status.status.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
