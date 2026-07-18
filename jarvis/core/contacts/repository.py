"""Contact Repository for Jarvis Core."""

from dataclasses import dataclass
from datetime import datetime
import re
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jarvis.core.events.event import BaseEvent
from jarvis.core.contacts.contact import (
    Contact,
    ContactRevision,
    contact_from_dict,
    contact_id_for_name,
    new_contact,
    normalize_contact_name,
    tuple_unique,
    tuple_unique_alias_records,
)
from jarvis.core.contacts.storage import InMemoryContactStorage
from jarvis.debug_trace import trace_event


@dataclass
class ContactChangeEvent:
    """One contact change event emitted by the repository."""

    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    revision: int
    changed_fields: tuple[str, ...]
    occurred_at: str
    trace_id: str = ""
    source: str = "manual"
    confidence: float = 1.0
    correlation_id: str = ""
    version: int = 1
    payload: dict = None
    metadata: dict = None

    @property
    def type(self):
        """Backward-compatible event type alias."""
        return self.event_type

    @property
    def contact_id(self):
        """Backward-compatible aggregate ID alias."""
        return self.aggregate_id

    @property
    def timestamp(self):
        """Backward-compatible occurred-at alias."""
        return self.occurred_at

    def to_dict(self):
        """Return event as a dict."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "revision": self.revision,
            "changed_fields": list(self.changed_fields),
            "occurred_at": self.occurred_at,
            "trace_id": self.trace_id,
            "source": self.source,
            "confidence": self.confidence,
            "correlation_id": self.correlation_id,
            "version": self.version,
            "payload": dict(self.payload or {}),
            "metadata": dict(self.metadata or {}),
        }

    def to_base_event(self):
        """Return this contact event as a Core BaseEvent."""
        return BaseEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            aggregate_type=self.aggregate_type,
            aggregate_id=self.aggregate_id,
            revision=self.revision,
            trace_id=self.trace_id,
            correlation_id=self.correlation_id,
            occurred_at=self.occurred_at,
            source=self.source,
            version=self.version,
            payload=dict(self.payload or {}),
            metadata=dict(self.metadata or {}),
        )


@dataclass
class ContactRepositoryMetrics:
    """Simple counters for contact operations."""

    contact_hit: int = 0
    contact_miss: int = 0
    contact_created: int = 0
    contact_updated: int = 0
    contact_deleted: int = 0
    contact_merged: int = 0
    contact_restored: int = 0
    event_count: int = 0
    revision_count: int = 0
    history_size: int = 0

    def to_dict(self):
        """Return metrics as a dict."""
        return {
            "contact_hit": self.contact_hit,
            "contact_miss": self.contact_miss,
            "contact_created": self.contact_created,
            "contact_updated": self.contact_updated,
            "contact_deleted": self.contact_deleted,
            "contact_merged": self.contact_merged,
            "contact_restored": self.contact_restored,
            "event_count": self.event_count,
            "revision_count": self.revision_count,
            "history_size": self.history_size,
        }


class ContactRepository:
    """Repository for canonical person contact entities."""

    def __init__(self, storage=None, seed_defaults=True, entity_graph=None, event_bus=None):
        """Create a repository."""
        self.storage = storage or InMemoryContactStorage()
        self.metrics = ContactRepositoryMetrics()
        self.contacts = {}
        self.entity_graph = entity_graph
        self.event_bus = event_bus
        self.events = []

        for contact in self.storage.load_all():
            self.contacts[contact.id] = contact

        if seed_defaults:
            self.seed_default_contacts()

    def seed_default_contacts(self):
        """Seed known local contacts without overwriting stored data."""
        for contact in [
            new_contact("아야", aliases=("あや", "Aya", "아이", "아야랑", "아야와", "아야한테"), source="manual", confidence=1.0),
            new_contact("유이", aliases=("Yui", "유이랑", "유이와"), source="manual", confidence=1.0),
            new_contact("유리", aliases=("Yuri", "유리랑", "유리와"), source="manual", confidence=1.0),
        ]:
            if contact.id not in self.contacts:
                self.contacts[contact.id] = contact

        self.persist()
        self.refresh_history_metrics()

    def list(self):
        """Return all contacts sorted by display name."""
        return sorted(self.contacts.values(), key=lambda contact: contact.display_name)

    def find_by_id(self, contact_id):
        """Return a contact by canonical ID."""
        contact = self.contacts.get(str(contact_id or ""))
        self.record_hit(contact, str(contact_id or ""))
        return contact

    def get(self, contact_id):
        """Backward-compatible alias for find_by_id."""
        return self.find_by_id(contact_id)

    def find_by_name(self, name):
        """Return a contact by display name or canonical name ID."""
        normalized = normalize_contact_name(name)
        contact = self.contacts.get(contact_id_for_name(normalized))

        if contact and contact.display_name == normalized:
            self.record_hit(contact, normalized)
            return contact

        for contact in self.contacts.values():
            if contact.display_name == normalized:
                self.record_hit(contact, normalized)
                return contact

        self.record_hit(None, normalized)
        return None

    def find_by_alias(self, alias):
        """Return a contact by alias."""
        normalized = normalize_contact_name(alias)

        for contact in self.contacts.values():
            if normalized in tuple_unique(contact.aliases):
                self.record_hit(contact, normalized)
                return contact

        self.record_hit(None, normalized)
        return None

    def resolve(self, text):
        """Resolve a display name or alias to a Contact."""
        query = normalize_contact_name(text)
        contact = self.find_by_name(query) or self.find_by_alias(query)

        if contact is not None:
            return contact

        for contact in self.contacts.values():
            aliases = tuple_unique((contact.display_name, *contact.aliases))

            if any(alias and alias in query for alias in aliases):
                self.record_hit(contact, query)
                return contact

        return None

    def create(self, display_name, **updates):
        """Create a contact, merging with an existing canonical entity when needed."""
        self.validate_updates(updates)
        contact = new_contact(display_name, **updates)
        existing = self.contacts.get(contact.id) or self.find_by_alias(display_name)

        if existing is not None:
            return self.merge(existing.id, contact)

        self.contacts[contact.id] = contact
        self.metrics.contact_created += 1
        contact = self.record_revision(contact, "created", ["id", "display_name"], contact.source, contact.confidence)
        self.contacts[contact.id] = contact
        self.persist()
        self.emit_event("ContactCreated", contact, ["id", "display_name"], contact.source, contact.confidence)
        self.after_change(contact)
        return contact

    def update(self, contact_id, **updates):
        """Patch one contact by ID."""
        existing = self.contacts.get(str(contact_id or ""))

        if existing is None:
            self.record_hit(None, contact_id)
            return None

        self.validate_updates(updates)
        self.enforce_contact_lock(existing, updates)
        changed_fields = changed_contact_fields(existing, updates)
        updated = merge_contact(existing, **updates)
        updated = self.record_revision(
            updated,
            "updated",
            changed_fields,
            str(updates.get("source") or updated.source),
            float(updates.get("confidence", updated.confidence)),
        )
        self.contacts[updated.id] = updated
        self.metrics.contact_updated += 1
        self.persist()
        self.emit_event("ContactUpdated", updated, changed_fields, updated.source, updated.confidence)
        self.after_change(updated)
        return updated

    def delete(self, contact_id):
        """Delete one contact by ID."""
        if contact_id not in self.contacts:
            self.record_hit(None, contact_id)
            return False

        contact = self.contacts.pop(contact_id)
        self.metrics.contact_deleted += 1
        self.persist()
        self.emit_event("ContactDeleted", contact, ["deleted"], contact.source, contact.confidence)
        self.after_change(None)
        return True

    def merge(self, canonical_id, incoming):
        """Merge an incoming contact or partial contact data into a canonical contact."""
        canonical_id = str(canonical_id or "")
        existing = self.contacts.get(canonical_id)

        if existing is None:
            contact = incoming if isinstance(incoming, Contact) else new_contact(str(incoming or ""), id=canonical_id)
            self.contacts[contact.id] = contact
            self.metrics.contact_created += 1
            contact = self.record_revision(contact, "created", ["id", "display_name"], contact.source, contact.confidence)
            self.contacts[contact.id] = contact
            self.persist()
            self.emit_event("ContactCreated", contact, ["id", "display_name"], contact.source, contact.confidence)
            self.after_change(contact)
            return contact

        updates = contact_to_update_dict(incoming)
        self.validate_updates(updates)
        self.enforce_contact_lock(existing, updates)
        merged = merge_contact(existing, **updates)
        merged = self.record_revision(merged, "merged", changed_contact_fields(existing, updates), merged.source, merged.confidence)
        self.contacts[merged.id] = merged
        self.metrics.contact_merged += 1
        self.persist()
        self.emit_event("ContactMerged", merged, ["merge"], merged.source, merged.confidence)
        self.after_change(merged)
        return merged

    def ensure(self, display_name, **updates):
        """Create or update a contact by display name or alias."""
        name = normalize_contact_name(display_name)
        existing = self.contacts.get(contact_id_for_name(name)) or self.find_by_name(name) or self.find_by_alias(name)

        if existing is None:
            return self.create(name, **updates)

        if name not in tuple_unique((existing.display_name, *existing.aliases)):
            updates["aliases"] = (*updates.get("aliases", ()), name)

        return self.update(existing.id, **updates)

    def get_revision_history(self, contact_id):
        """Return revision history for a contact."""
        contact = self.contacts.get(str(contact_id or ""))
        return list(contact.revision_history) if contact else []

    def latest_revision(self, contact_id):
        """Return the latest revision number for a contact."""
        contact = self.contacts.get(str(contact_id or ""))
        return contact.revision if contact else 0

    def restore_revision(self, contact_id, revision):
        """Restore a contact snapshot from revision history."""
        contact = self.contacts.get(str(contact_id or ""))

        if contact is None:
            self.record_hit(None, contact_id)
            return None

        target = next((item for item in contact.revision_history if item.revision == int(revision)), None)

        if target is None or not target.snapshot:
            self.record_hit(None, f"{contact_id}:r{revision}")
            return None

        restored = contact_from_dict(target.snapshot)
        restored = restored.with_updates(
            revision=contact.revision + 1,
            revision_history=contact.revision_history,
            source=target.source,
            confidence=target.confidence,
        )
        restored = self.record_revision(restored, "restored", ["revision"], target.source, target.confidence)
        self.contacts[restored.id] = restored
        self.metrics.contact_restored += 1
        self.persist()
        self.emit_event("ContactRestored", restored, ["revision"], restored.source, restored.confidence)
        self.after_change(restored)
        return restored

    def undo_last_change(self, contact_id):
        """Restore the previous revision when available."""
        history = self.get_revision_history(contact_id)

        if len(history) < 2:
            return None

        return self.restore_revision(contact_id, history[-2].revision)

    def update_email(self, name, email):
        """Store an email address for a contact."""
        contact = self.resolve(name)
        emails = (*contact.emails, email) if contact else (email,)
        return self.ensure(name, emails=emails)

    def update_phone(self, name, phone):
        """Store a phone number for a contact."""
        contact = self.resolve(name)
        phones = (*contact.phones, phone) if contact else (phone,)
        return self.ensure(name, phones=phones)

    def update_birthday(self, name, birthday):
        """Store a birthday for a contact."""
        return self.ensure(name, birthday=birthday)

    def resolve_participant_ids(self, participants):
        """Return contact IDs for known participant names, keeping unknown names as-is."""
        resolved = []

        for participant in participants or []:
            contact = self.resolve(participant)
            resolved.append(contact.id if contact else participant)

        return resolved

    def known_entities(self):
        """Return contacts as KnownEntity-compatible objects."""
        return list(self.contacts.values())

    def known_entities_version(self):
        """Return a cache-version string based on contact revisions."""
        parts = [f"{contact.id}:r{contact.revision}" for contact in self.list()]
        return "contacts:" + "|".join(parts)

    def record_interaction(self, contact_id, kind, timestamp=None):
        """Record a lightweight interaction marker."""
        contact = self.contacts.get(str(contact_id or ""))

        if contact is None:
            self.record_hit(None, contact_id)
            return None

        key = f"last_{kind}"
        metadata = dict(contact.metadata)
        metadata[key] = timestamp or current_timestamp()
        metadata["interaction_count"] = int(metadata.get("interaction_count", 0)) + 1
        return self.update(contact.id, metadata=metadata, source="system", confidence=1.0)

    def record_revision(self, contact, action, changed_fields, source, confidence):
        """Append one revision snapshot to a contact."""
        snapshot = contact.to_dict()
        snapshot.pop("revision_history", None)
        revision = ContactRevision(
            revision=contact.revision,
            timestamp=current_timestamp(),
            action=action,
            changed_fields=tuple_unique(changed_fields),
            source=str(source or "manual"),
            confidence=float(confidence),
            snapshot=snapshot,
        )
        history = tuple_unique_revisions_by_revision((*contact.revision_history, revision))
        return contact.with_updates(revision=contact.revision, revision_history=history)

    def emit_event(self, event_type, contact, changed_fields, source, confidence):
        """Record and trace one contact change event."""
        if contact is None:
            return

        event = ContactChangeEvent(
            event_id=new_event_id(),
            event_type=event_type,
            aggregate_type="contact",
            aggregate_id=contact.id,
            revision=contact.revision,
            changed_fields=tuple_unique(changed_fields),
            occurred_at=current_timestamp(),
            trace_id="",
            source=str(source or "manual"),
            confidence=float(confidence),
            correlation_id="",
            version=1,
            payload={"contact": contact.to_dict(), "changed_fields": list(tuple_unique(changed_fields))},
            metadata={"confidence": float(confidence)},
        )
        self.events.append(event)
        trace_event(
            "contact.event",
            event_id=event.event_id,
            event_type=event.event_type,
            id=event.aggregate_id,
            revision=event.revision,
            changed=",".join(event.changed_fields),
            source=event.source,
            confidence=event.confidence,
            correlation_id=event.correlation_id,
        )
        if self.event_bus is not None:
            self.event_bus.publish(event.to_base_event())

    def after_change(self, contact):
        """Sync side effects after contact mutation."""
        self.sync_entity_graph(contact)
        self.refresh_history_metrics()
        trace_event("contact.metrics", **self.metrics.to_dict())

    def sync_entity_graph(self, contact):
        """Patch the entity graph from a contact when configured."""
        if self.entity_graph is None or contact is None:
            return None

        from jarvis.core.contacts.resolver import sync_contact_to_graph

        return sync_contact_to_graph(self.entity_graph, contact)

    def refresh_history_metrics(self):
        """Refresh aggregate revision metrics."""
        self.metrics.revision_count = sum(contact.revision for contact in self.contacts.values())
        self.metrics.history_size = sum(len(contact.revision_history) for contact in self.contacts.values())
        self.metrics.event_count = len(self.events)

    def validate_updates(self, updates):
        """Validate contact fields before save."""
        for email in updates.get("emails") or ():
            if not is_valid_email(email):
                raise ValueError(f"invalid_email:{email}")

        for phone in updates.get("phones") or ():
            if not is_valid_phone(phone):
                raise ValueError(f"invalid_phone:{phone}")

        birthday = str(updates.get("birthday") or "")
        if birthday and not is_valid_birthday(birthday):
            raise ValueError(f"invalid_birthday:{birthday}")

        country = str(updates.get("country") or "")
        if country and len(country) < 2:
            raise ValueError(f"invalid_country:{country}")

        language = str(updates.get("language") or "")
        if language and not re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", language):
            raise ValueError(f"invalid_language:{language}")

        timezone = str(updates.get("timezone") or "")
        if timezone and not is_valid_timezone(timezone):
            raise ValueError(f"invalid_timezone:{timezone}")

    def enforce_contact_lock(self, contact, updates):
        """Prevent low-confidence writes to verified core facts."""
        protected_fields = {"emails", "phones", "birthday", "country", "timezone", "language"}
        changed = protected_fields.intersection(set(updates.keys()))

        if not contact.verified or not changed:
            return

        source = str(updates.get("source") or "")
        confidence = confidence_score(source, updates.get("confidence", contact.confidence))

        if source in {"user_confirmed", "manual_confirmed"}:
            return

        if source in {"llm_guess", "ai_guess"} or confidence < 0.98:
            raise PermissionError("verified_contact_update_requires_confirmation")

    def persist(self):
        """Persist current contacts."""
        self.storage.save_all(self.list())

    def record_hit(self, contact, query):
        """Record hit/miss trace for one lookup."""
        if contact is None:
            self.metrics.contact_miss += 1
            trace_event("contact.miss", query=query)
        else:
            self.metrics.contact_hit += 1
            trace_event("contact.matched", query=query, id=contact.id, name=contact.display_name)
        trace_event("contact.metrics", **self.metrics.to_dict())


def contact_to_update_dict(value):
    """Return merge updates from a Contact or dict."""
    if isinstance(value, Contact):
        return {
            "alias_records": value.alias_records,
            "aliases": value.aliases,
            "emails": value.emails,
            "phones": value.phones,
            "birthday": value.birthday,
            "tags": value.tags,
            "notes": value.notes,
            "metadata": value.metadata,
            "language": value.language,
            "timezone": value.timezone,
            "country": value.country,
            "favorite": value.favorite,
            "importance": value.importance,
            "source": value.source,
            "confidence": value.confidence,
            "verified": value.verified,
        }
    return dict(value or {})


def merge_contact(contact, **updates):
    """Merge partial updates into one contact."""
    aliases = tuple_unique((*contact.aliases, *(updates.get("aliases") or ())))
    alias_records = tuple_unique_alias_records((*contact.alias_records, *(updates.get("alias_records") or ())))
    emails = tuple_unique((*contact.emails, *(updates.get("emails") or ())))
    phones = tuple_unique((*contact.phones, *(updates.get("phones") or ())))
    tags = tuple_unique((*contact.tags, *(updates.get("tags") or ())))
    metadata = dict(contact.metadata)
    metadata.update(dict(updates.get("metadata") or {}))
    source = str(updates.get("source") or contact.source)
    confidence = max(float(updates.get("confidence", contact.confidence)), contact.confidence)
    verified = bool(updates.get("verified", contact.verified))

    return contact.with_updates(
        aliases=aliases,
        alias_records=alias_records,
        emails=emails,
        phones=phones,
        birthday=str(updates.get("birthday") or contact.birthday),
        tags=tags,
        notes=str(updates.get("notes") or contact.notes),
        metadata=metadata,
        language=str(updates.get("language") or contact.language),
        timezone=str(updates.get("timezone") or contact.timezone),
        country=str(updates.get("country") or contact.country),
        favorite=bool(updates["favorite"]) if "favorite" in updates else contact.favorite,
        importance=str(updates.get("importance") or contact.importance),
        source=source,
        confidence=confidence,
        verified=verified,
    )


def changed_contact_fields(contact, updates):
    """Return user-facing fields that changed in an update payload."""
    changed = []

    for key, value in (updates or {}).items():
        if key in {"source", "confidence"}:
            continue
        if key in {"aliases", "emails", "phones", "tags"}:
            old_value = tuple_unique(getattr(contact, key, ()))
            new_value = tuple_unique((*old_value, *(value or ())))
        elif key == "alias_records":
            old_value = tuple_unique_alias_records(getattr(contact, key, ()))
            new_value = tuple_unique_alias_records((*old_value, *(value or ())))
        elif key == "metadata":
            old_value = dict(contact.metadata)
            new_value = dict(contact.metadata)
            new_value.update(dict(value or {}))
        else:
            old_value = getattr(contact, key, None)
            new_value = value

        if old_value != new_value:
            changed.append(key)

    return tuple_unique(changed) or ("revision",)


def confidence_score(source, explicit_confidence=None):
    """Return source-aware confidence."""
    if explicit_confidence is not None:
        return float(explicit_confidence)

    source_confidence = {
        "manual": 1.0,
        "user": 1.0,
        "google_contacts": 0.98,
        "contacts": 0.98,
        "memory": 0.90,
        "llm_guess": 0.70,
        "ai_guess": 0.70,
    }
    return source_confidence.get(str(source or "").lower(), 0.80)


def is_valid_email(value):
    """Return whether value looks like an email address."""
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(value or "")))


def is_valid_phone(value):
    """Return whether value looks like a phone number."""
    digits = re.sub(r"\D", "", str(value or ""))
    return 8 <= len(digits) <= 16


def is_valid_birthday(value):
    """Return whether birthday is MM-DD or YYYY-MM-DD."""
    text = str(value or "")

    try:
        if re.fullmatch(r"\d{2}-\d{2}", text):
            datetime.strptime(f"2000-{text}", "%Y-%m-%d")
            return True
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            datetime.strptime(text, "%Y-%m-%d")
            return True
    except ValueError:
        return False

    return False


def is_valid_timezone(value):
    """Return whether a timezone name is available."""
    text = str(value or "")

    if re.fullmatch(r"[A-Za-z_]+/[A-Za-z0-9_+\-]+(?:/[A-Za-z0-9_+\-]+)?", text):
        return True

    try:
        ZoneInfo(text)
    except ZoneInfoNotFoundError:
        return False
    return True


def current_timestamp():
    """Return a compact ISO timestamp."""
    return datetime.now().isoformat(timespec="seconds")


def new_event_id():
    """Return a compact contact event ID."""
    return f"CE-{uuid.uuid4().hex[:8].upper()}"


def tuple_unique_revisions_by_revision(values):
    """Return revision records deduped by revision number."""
    by_revision = {}

    for item in values or ():
        by_revision[item.revision] = item

    return tuple(by_revision[key] for key in sorted(by_revision))
