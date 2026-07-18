import json
from pathlib import Path
from time import perf_counter

from jarvis.abilities.metadata import AbilityMetadata, AbilityType
from jarvis.abilities.native.contacts.formatter import (
    confirmation_message,
)
from jarvis.abilities.native.contacts.parser import ContactIntentParser, normalize_query
from jarvis.abilities.native.contacts.result import ContactResult
from jarvis.abilities.result import AbilityHealth, AbilityResult
from jarvis.core.contacts import ContactRepository
from jarvis.debug_trace import trace_event
from jarvis.permissions import PermissionLevel


CONFIRM_REQUIRED_ACTIONS = {"create", "update", "delete", "merge"}


class ContactAbility:
    """Native Contact Ability backed by ContactRepository."""

    def __init__(self, repository=None, metadata=None, parser=None):
        """Create Contact Ability."""
        self.repository = repository or ContactRepository()
        self.metadata = metadata or load_contact_metadata()
        self.parser = parser or ContactIntentParser()

    @property
    def id(self):
        """Return ability ID."""
        return self.metadata.id

    @property
    def name(self):
        """Return ability display name."""
        return self.metadata.name

    @property
    def type(self):
        """Return ability type."""
        return self.metadata.type

    @property
    def description(self):
        """Return ability description."""
        return self.metadata.description

    @property
    def permission(self):
        """Return base permission."""
        return self.metadata.permission

    def execute(self, input_data):
        """Execute a contact action and return AbilityResult."""
        started = perf_counter()

        try:
            query = normalize_query(input_data, self.parser)
            correlation_id = extract_correlation_id(input_data)
            trace_event(
                "contact.query",
                action=query.action,
                contact_id=query.contact_id,
                display_name=query.display_name,
                attribute=query.attribute,
            )

            if query.action in CONFIRM_REQUIRED_ACTIONS and not query.confirmed:
                trace_event("contact.permission", action=query.action, permission="confirm_required")
                result = ContactResult(
                    success=True,
                    action=query.action,
                    changed_fields=query_changed_fields(query),
                    provider=self.provider_name,
                    correlation_id=correlation_id,
                    execution_time_ms=elapsed_ms(started),
                    message=confirmation_message(query),
                    requires_confirmation=True,
                )
                return AbilityResult(
                    success=True,
                    data=result,
                    metadata={"ability_id": self.id, "query": query, "permission": "confirm_required"},
                )

            result = attach_runtime_fields(
                self.execute_query(query),
                provider=self.provider_name,
                correlation_id=correlation_id,
                execution_time_ms=elapsed_ms(started),
            )
            trace_event(
                "contact.result",
                action=result.action,
                success=result.success,
                contact_id=getattr(result.contact, "id", query.contact_id),
                error_code=result.error_code,
                provider=result.provider,
                execution_time_ms=result.execution_time_ms,
                correlation_id=result.correlation_id,
            )
            return AbilityResult(
                success=result.success,
                data=result,
                error=result.message if not result.success else "",
                metadata={"ability_id": self.id, "query": query},
            )
        except Exception as error:
            return AbilityResult(success=False, error=str(error), metadata={"ability_id": self.id})

    @property
    def provider_name(self):
        """Return the current contact backend provider name."""
        storage = getattr(self.repository, "storage", None)
        name = getattr(storage, "provider_name", "")

        if name:
            return name

        return storage_provider_name(storage)

    def execute_query(self, query):
        """Execute one normalized ContactQuery."""
        if query.action == "create":
            contact = self.repository.ensure(query.display_name, aliases=query.aliases, source=query.source)
            return self.create_result("create", contact, changed_fields=("id", "display_name"))

        if query.action == "update":
            contact = self.update_contact(query)
            return self.create_result("update", contact, changed_fields=query_changed_fields(query))

        if query.action == "get":
            contact = self.resolve_contact(query)
            return ContactResult(
                success=contact is not None,
                action="get",
                contact=contact,
                changed_fields=(query.attribute,),
                error_code="" if contact is not None else "contact_not_found",
                revision=getattr(contact, "revision", 0) if contact is not None else 0,
            trace_id=latest_contact_event_id(self.repository, getattr(contact, "id", "")) if contact is not None else "",
        )

        if query.action == "delete":
            contact = self.resolve_contact(query)

            if contact is None:
                return ContactResult(success=False, action="delete", error_code="contact_not_found")

            deleted = self.repository.delete(contact.id)
            return ContactResult(
                success=deleted,
                action="delete",
                contact=contact,
                changed_fields=("deleted",),
                revision=getattr(contact, "revision", 0),
                event_id=latest_contact_event_id(self.repository, contact.id),
            trace_id=latest_contact_event_id(self.repository, contact.id),
            error_code="" if deleted else "delete_failed",
        )

        if query.action == "list":
            contacts = tuple(self.repository.list())
            return ContactResult(success=True, action="list", contacts=contacts)

        raise ValueError(f"Unsupported contact action: {query.action}")

    def update_contact(self, query):
        """Apply one contact update."""
        contact = self.resolve_contact(query)
        name = query.display_name or query.contact_id

        updates = {"source": query.source}

        if query.email:
            emails = (*contact.emails, query.email) if contact else (query.email,)
            updates["emails"] = emails

        if query.phone:
            phones = (*contact.phones, query.phone) if contact else (query.phone,)
            updates["phones"] = phones

        if query.birthday:
            updates["birthday"] = query.birthday

        if query.aliases:
            updates["aliases"] = query.aliases

        return self.repository.ensure(name, **updates)

    def create_result(self, action, contact, changed_fields):
        """Create a structured ContactResult from repository state."""
        event_id = latest_contact_event_id(self.repository, getattr(contact, "id", ""))
        return ContactResult(
            success=True,
            action=action,
            contact=contact,
            changed_fields=tuple(changed_fields or ()),
            revision=getattr(contact, "revision", 0),
            event_id=event_id,
            trace_id=event_id,
            provider=self.provider_name,
        )

    def resolve_contact(self, query):
        """Resolve a query to a Contact."""
        if query.contact_id:
            contact = self.repository.find_by_id(query.contact_id)
            if contact is not None:
                return contact

        if query.display_name:
            return self.repository.resolve(query.display_name)

        return None

    def health(self):
        """Return repository health."""
        return AbilityHealth(status="ok", provider="contact_repository", message="Contact repository is ready.")


def load_contact_metadata():
    """Load Contact manifest."""
    manifest_path = Path(__file__).with_name("manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    return AbilityMetadata(
        id=manifest["id"],
        name=manifest["name"],
        type=AbilityType(manifest["type"]),
        permission=PermissionLevel(manifest["permission"]),
        version=manifest["version"],
        author=manifest.get("author", "Jarvis"),
        description=manifest["description"],
        capabilities=list(manifest.get("capabilities", [])),
        input_schema=dict(manifest.get("input_schema", {})),
        output_schema=manifest.get("output_schema", "ContactResult"),
        aliases=list(manifest.get("aliases", [])),
        supported_intents=list(manifest.get("supported_intents", [])),
        examples=list(manifest.get("examples", [])),
        input_prefixes=list(manifest.get("input_prefixes", [])),
        route_confidence=float(manifest.get("route_confidence", 0.75)),
    )


def create_ability(repository=None):
    """Create Contact Ability."""
    return ContactAbility(repository=repository)


def query_changed_fields(query):
    """Return fields represented by a ContactQuery."""
    fields = []

    if query.email:
        fields.append("emails")
    if query.phone:
        fields.append("phones")
    if query.birthday:
        fields.append("birthday")
    if query.aliases:
        fields.append("aliases")
    if query.attribute and query.action == "get":
        fields.append(query.attribute)

    return tuple(fields)


def latest_contact_event_id(repository, contact_id):
    """Return the latest event ID for one contact."""
    for event in reversed(getattr(repository, "events", []) or []):
        if getattr(event, "aggregate_id", "") == contact_id:
            return getattr(event, "event_id", "")

    return ""


def attach_runtime_fields(result, provider, correlation_id, execution_time_ms):
    """Return ContactResult with runtime fields populated."""
    from dataclasses import replace

    return replace(
        result,
        provider=provider,
        correlation_id=correlation_id,
        execution_time_ms=int(execution_time_ms),
    )


def extract_correlation_id(input_data):
    """Return correlation ID from input metadata when present."""
    if isinstance(input_data, dict):
        return str(input_data.get("correlation_id") or input_data.get("trace_id") or "")

    return ""


def storage_provider_name(storage):
    """Return a stable provider name for the repository storage."""
    class_name = storage.__class__.__name__ if storage is not None else ""

    if class_name == "InMemoryContactStorage":
        return "memory"

    if class_name == "JsonContactStorage":
        return "json"

    return "contact_repository"


def elapsed_ms(started):
    """Return elapsed milliseconds from perf_counter start."""
    return int((perf_counter() - started) * 1000)
