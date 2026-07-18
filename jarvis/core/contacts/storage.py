"""Storage providers for Contact Repository."""

import json
from pathlib import Path
from typing import Protocol

from jarvis.core.contacts.contact import Contact, contact_from_dict


class ContactStorage(Protocol):
    """Storage contract for contacts."""

    def load_all(self) -> list[Contact]:
        """Return all stored contacts."""

    def save_all(self, contacts: list[Contact]) -> None:
        """Persist all contacts."""


class InMemoryContactStorage:
    """In-memory contact storage for tests and runtime defaults."""

    def __init__(self, contacts=None):
        """Create storage with optional contacts."""
        self.contacts = list(contacts or [])

    def load_all(self):
        """Return all contacts."""
        return list(self.contacts)

    def save_all(self, contacts):
        """Replace all contacts."""
        self.contacts = list(contacts or [])


class JsonContactStorage:
    """JSON file contact storage."""

    def __init__(self, path="contacts/contacts.json"):
        """Create storage at a path."""
        self.path = Path(path)

    def load_all(self):
        """Load all contacts from disk."""
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        return [contact_from_dict(item) for item in raw.get("contacts", [])]

    def save_all(self, contacts):
        """Save all contacts to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"contacts": [contact.to_dict() for contact in contacts]}

        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
