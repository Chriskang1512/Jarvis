from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContactQuery:
    """Structured input for Contact Ability."""

    action: str = "get"
    contact_id: str = ""
    display_name: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)
    email: str = ""
    phone: str = ""
    birthday: str = ""
    attribute: str = "contact"
    external_id: str = ""
    source: str = "user"
    confirmed: bool = False
    raw_text: str = ""

    def to_input_data(self):
        """Return a dispatcher-safe dictionary."""
        return {
            "action": self.action,
            "contact_id": self.contact_id,
            "display_name": self.display_name,
            "aliases": list(self.aliases),
            "email": self.email,
            "phone": self.phone,
            "birthday": self.birthday,
            "attribute": self.attribute,
            "external_id": self.external_id,
            "source": self.source,
            "confirmed": self.confirmed,
            "raw_text": self.raw_text,
        }
