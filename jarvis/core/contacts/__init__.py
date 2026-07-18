"""Contact entity foundation for Jarvis Core."""

from jarvis.core.contacts.contact import Contact, ContactAlias, ContactRevision, contact_from_dict, contact_id_for_name, normalize_contact_name
from jarvis.core.contacts.repository import ContactChangeEvent, ContactRepository, ContactRepositoryMetrics
from jarvis.core.contacts.resolver import ContactCommand, ContactCommandParser, ContactResolver
from jarvis.core.contacts.storage import InMemoryContactStorage, JsonContactStorage

__all__ = [
    "Contact",
    "ContactAlias",
    "ContactRevision",
    "ContactCommand",
    "ContactCommandParser",
    "ContactRepository",
    "ContactChangeEvent",
    "ContactRepositoryMetrics",
    "ContactResolver",
    "InMemoryContactStorage",
    "JsonContactStorage",
    "contact_from_dict",
    "contact_id_for_name",
    "normalize_contact_name",
]
