"""Manual Google Contacts read smoke test.

This script bypasses voice/STT and checks the Google People API provider
directly, which helps separate account/provider issues from transcript issues.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis.abilities.native.contacts.query import ContactQuery
from jarvis.providers.google.config import GOOGLE_CONTACTS_READONLY_SCOPE, GoogleProviderConfig
from jarvis.providers.google.contacts import GoogleContactsProvider


def main():
    """Run one Google Contacts provider smoke check."""
    configure_console_encoding()
    args = parse_args()
    query = args.query or decode_query_escape(args.query_escape)

    provider = GoogleContactsProvider(
        config=GoogleProviderConfig(
            credentials_path=os.environ.get("JARVIS_GOOGLE_CREDENTIALS_PATH", "data/credentials/google_token.json"),
            client_secret_path=os.environ.get("JARVIS_GOOGLE_CLIENT_SECRET_PATH", "client_secret.json"),
            scopes=(GOOGLE_CONTACTS_READONLY_SCOPE,),
        )
    )

    if query:
        result = provider.get_contact(ContactQuery(action="get", display_name=query, attribute=args.attribute))
    else:
        result = provider.list_contacts(SimpleNamespace(action="list", limit=args.limit))

    payload = result_payload(result)
    print(json.dumps(payload, ensure_ascii=not args.raw_unicode, indent=2))


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Google Contacts provider smoke test")
    parser.add_argument("--query", default="", help="Contact name to search")
    parser.add_argument("--query-escape", default="", help=r"Unicode-escaped contact name, e.g. \uc6b0\uc218")
    parser.add_argument("--attribute", default="contact", choices=["contact", "phone", "email", "birthday"])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--raw-unicode", action="store_true", help="Print UTF-8 instead of JSON escapes")
    return parser.parse_args()


def decode_query_escape(value):
    """Decode a unicode_escape query without relying on console input encoding."""
    if not value:
        return ""

    return value.encode("ascii").decode("unicode_escape")


def result_payload(result):
    """Return a safe JSON payload for one ContactResult."""
    contacts = [contact.to_dict() for contact in tuple(getattr(result, "contacts", ()) or ())]
    contact = getattr(result, "contact", None)
    return {
        "success": bool(getattr(result, "success", False)),
        "action": getattr(result, "action", ""),
        "provider": getattr(result, "provider", ""),
        "error_code": getattr(result, "error_code", ""),
        "message": getattr(result, "message", ""),
        "execution_time_ms": getattr(result, "execution_time_ms", 0),
        "contact": contact.to_dict() if contact is not None else None,
        "contacts": contacts,
        "contacts_count": len(contacts),
    }


def configure_console_encoding():
    """Use UTF-8 streams when available."""
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleCP(65001)
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()
