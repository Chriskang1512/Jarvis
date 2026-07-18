from dataclasses import dataclass, field

from jarvis.abilities.result import BaseAbilityResult


@dataclass(frozen=True)
class ContactResult(BaseAbilityResult):
    """Structured Contact Ability result.

    Formatter owns user-facing language. This object is the durable
    contract for history, undo, Event Bus, and future sync providers.
    """

    action: str = ""
    contact: object = None
    contacts: tuple[object, ...] = field(default_factory=tuple)
    changed_fields: tuple[str, ...] = field(default_factory=tuple)
    revision: int = 0
    event_id: str = ""
    message: str = ""
    requires_confirmation: bool = False
    provider: str = "contact_repository"

    def to_natural_language(self):
        """Return the formatted response without embedding language here."""
        from jarvis.abilities.native.contacts.formatter import format_contact_result

        return format_contact_result(self)
