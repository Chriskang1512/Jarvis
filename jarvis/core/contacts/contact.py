"""Contact entity model."""

from dataclasses import dataclass, field, replace
from datetime import datetime
import re


CONTACT_TYPE_PERSON = "person"


@dataclass(frozen=True)
class ContactAlias:
    """A typed alias for one contact."""

    value: str
    type: str = "nickname"
    source: str = "manual"
    confidence: float = 1.0

    def to_dict(self):
        """Return a JSON-serializable alias."""
        return {
            "value": self.value,
            "type": self.type,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ContactRevision:
    """One immutable contact revision record."""

    revision: int
    timestamp: str
    action: str
    changed_fields: tuple[str, ...] = field(default_factory=tuple)
    source: str = "manual"
    confidence: float = 1.0
    snapshot: dict = field(default_factory=dict)

    def to_dict(self):
        """Return a JSON-serializable revision."""
        return {
            "revision": self.revision,
            "timestamp": self.timestamp,
            "action": self.action,
            "changed_fields": list(self.changed_fields),
            "source": self.source,
            "confidence": self.confidence,
            "snapshot": dict(self.snapshot),
        }


@dataclass(frozen=True)
class Contact:
    """One person known to Jarvis."""

    id: str
    display_name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    alias_records: tuple[ContactAlias, ...] = field(default_factory=tuple)
    emails: tuple[str, ...] = field(default_factory=tuple)
    phones: tuple[str, ...] = field(default_factory=tuple)
    birthday: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""
    metadata: dict = field(default_factory=dict)
    language: str = ""
    timezone: str = ""
    country: str = ""
    favorite: bool = False
    importance: str = ""
    source: str = "manual"
    confidence: float = 1.0
    verified: bool = False
    revision: int = 1
    revision_history: tuple[ContactRevision, ...] = field(default_factory=tuple)
    created_at: str = ""
    updated_at: str = ""

    def with_updates(self, **updates):
        """Return a copy with normalized collection fields and updated timestamp."""
        now = current_timestamp()
        normalized = dict(updates)

        for key in ["aliases", "emails", "phones", "tags"]:
            if key in normalized:
                normalized[key] = tuple_unique(normalized[key])

        if "alias_records" in normalized:
            normalized["alias_records"] = tuple_unique_alias_records(normalized["alias_records"])

        if "metadata" in normalized:
            normalized["metadata"] = dict(normalized["metadata"] or {})

        if "revision_history" in normalized:
            normalized["revision_history"] = tuple_unique_revisions(normalized["revision_history"])

        normalized["revision"] = int(normalized.get("revision", self.revision + 1))
        return replace(self, updated_at=now, **normalized)

    def to_dict(self):
        """Return a JSON-serializable contact."""
        return {
            "id": self.id,
            "display_name": self.display_name,
            "aliases": list(self.aliases),
            "alias_records": [alias.to_dict() for alias in self.alias_records],
            "emails": list(self.emails),
            "phones": list(self.phones),
            "birthday": self.birthday,
            "tags": list(self.tags),
            "notes": self.notes,
            "metadata": dict(self.metadata),
            "language": self.language,
            "timezone": self.timezone,
            "country": self.country,
            "favorite": self.favorite,
            "importance": self.importance,
            "source": self.source,
            "confidence": self.confidence,
            "verified": self.verified,
            "revision": self.revision,
            "revision_history": [revision.to_dict() for revision in self.revision_history],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def new_contact(display_name, **kwargs):
    """Create a normalized Contact from user-facing fields."""
    now = current_timestamp()
    name = normalize_contact_name(display_name)
    aliases = tuple_unique((name, *(kwargs.get("aliases") or ())))
    alias_records = build_alias_records(name, aliases, kwargs.get("alias_records") or ())
    contact_id = kwargs.get("id") or contact_id_for_name(name)
    return Contact(
        id=contact_id,
        display_name=name,
        aliases=aliases,
        alias_records=alias_records,
        emails=tuple_unique(kwargs.get("emails") or ()),
        phones=tuple_unique(kwargs.get("phones") or ()),
        birthday=str(kwargs.get("birthday") or ""),
        tags=tuple_unique(kwargs.get("tags") or ()),
        notes=str(kwargs.get("notes") or ""),
        metadata=dict(kwargs.get("metadata") or {}),
        language=str(kwargs.get("language") or ""),
        timezone=str(kwargs.get("timezone") or ""),
        country=str(kwargs.get("country") or ""),
        favorite=bool(kwargs.get("favorite", False)),
        importance=str(kwargs.get("importance") or ""),
        source=str(kwargs.get("source") or "manual"),
        confidence=float(kwargs.get("confidence", 1.0)),
        verified=bool(kwargs.get("verified", False)),
        revision=int(kwargs.get("revision", 1)),
        revision_history=tuple_unique_revisions(kwargs.get("revision_history") or ()),
        created_at=str(kwargs.get("created_at") or now),
        updated_at=str(kwargs.get("updated_at") or now),
    )


def contact_from_dict(data):
    """Load a Contact from serialized data."""
    data = dict(data or {})
    return Contact(
        id=str(data.get("id") or contact_id_for_name(data.get("display_name", ""))),
        display_name=normalize_contact_name(data.get("display_name", "")),
        aliases=tuple_unique(data.get("aliases") or ()),
        alias_records=tuple_unique_alias_records(data.get("alias_records") or build_alias_records(data.get("display_name", ""), data.get("aliases") or (), ())),
        emails=tuple_unique(data.get("emails") or ()),
        phones=tuple_unique(data.get("phones") or ()),
        birthday=str(data.get("birthday") or ""),
        tags=tuple_unique(data.get("tags") or ()),
        notes=str(data.get("notes") or ""),
        metadata=dict(data.get("metadata") or {}),
        language=str(data.get("language") or ""),
        timezone=str(data.get("timezone") or ""),
        country=str(data.get("country") or ""),
        favorite=bool(data.get("favorite", False)),
        importance=str(data.get("importance") or ""),
        source=str(data.get("source") or "manual"),
        confidence=float(data.get("confidence", 1.0)),
        verified=bool(data.get("verified", False)),
        revision=int(data.get("revision", 1)),
        revision_history=tuple_unique_revisions(data.get("revision_history") or ()),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
    )


def normalize_contact_name(value):
    """Normalize a spoken contact name without changing identity."""
    return " ".join(str(value or "").strip().split())


def contact_id_for_name(name):
    """Return a stable canonical contact ID for a display name or alias."""
    normalized = normalize_contact_name(name)
    slug = canonical_contact_slugs().get(normalized)

    if slug is None:
        slug = re.sub(r"\s+", "_", normalized.lower())
        slug = re.sub(r"[^\w가-힣ぁ-んァ-ン一-龥_-]", "", slug)

    return f"person_{slug or 'unknown'}"


def canonical_contact_slugs():
    """Return stable canonical slugs for common local contacts and aliases."""
    return {
        "아야": "aya",
        "Aya": "aya",
        "aya": "aya",
        "あや": "aya",
        "アヤ": "aya",
        "유이": "yui",
        "Yui": "yui",
        "yui": "yui",
        "유리": "yuri",
        "Yuri": "yuri",
        "yuri": "yuri",
        "엄마": "mom",
        "형": "older_brother",
    }


def tuple_unique(values):
    """Return non-empty unique string values in order."""
    unique = []

    for value in values or ():
        text = normalize_contact_name(value)

        if text and text not in unique:
            unique.append(text)

    return tuple(unique)


def tuple_unique_alias_records(values):
    """Return unique ContactAlias objects by value/type/source."""
    unique = []
    seen = set()

    for value in values or ():
        alias = contact_alias_from_value(value)
        key = (alias.value, alias.type, alias.source)

        if alias.value and key not in seen:
            seen.add(key)
            unique.append(alias)

    return tuple(unique)


def tuple_unique_revisions(values):
    """Return ContactRevision objects sorted by revision."""
    revisions = []
    seen = set()

    for value in values or ():
        revision = contact_revision_from_value(value)

        if revision.revision not in seen:
            seen.add(revision.revision)
            revisions.append(revision)

    return tuple(sorted(revisions, key=lambda item: item.revision))


def build_alias_records(display_name, aliases, alias_records):
    """Create typed alias records from display name and legacy aliases."""
    records = [ContactAlias(normalize_contact_name(display_name), type="official", source="manual")]

    for alias in aliases or ():
        if normalize_contact_name(alias) == normalize_contact_name(display_name):
            continue
        alias_type = infer_alias_type(alias)
        records.append(ContactAlias(normalize_contact_name(alias), type=alias_type, source="manual"))

    records.extend(contact_alias_from_value(alias) for alias in alias_records or ())
    return tuple_unique_alias_records(records)


def contact_alias_from_value(value):
    """Convert a dict, ContactAlias, or string into ContactAlias."""
    if isinstance(value, ContactAlias):
        return value

    if isinstance(value, dict):
        return ContactAlias(
            value=normalize_contact_name(value.get("value", "")),
            type=str(value.get("type") or "nickname"),
            source=str(value.get("source") or "manual"),
            confidence=float(value.get("confidence", 1.0)),
        )

    text = normalize_contact_name(value)
    return ContactAlias(value=text, type=infer_alias_type(text), source="manual")


def contact_revision_from_value(value):
    """Convert a dict or ContactRevision into ContactRevision."""
    if isinstance(value, ContactRevision):
        return value

    data = dict(value or {})
    return ContactRevision(
        revision=int(data.get("revision", 0)),
        timestamp=str(data.get("timestamp") or ""),
        action=str(data.get("action") or ""),
        changed_fields=tuple_unique(data.get("changed_fields") or ()),
        source=str(data.get("source") or "manual"),
        confidence=float(data.get("confidence", 1.0)),
        snapshot=dict(data.get("snapshot") or {}),
    )


def infer_alias_type(value):
    """Infer a coarse alias type."""
    text = str(value or "")

    if re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", text):
        return "romanized"

    if re.search(r"[ぁ-んァ-ン]", text):
        return "official"

    return "nickname"


def current_timestamp():
    """Return a compact ISO timestamp."""
    return datetime.now().isoformat(timespec="seconds")
