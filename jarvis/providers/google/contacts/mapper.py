"""Map Google People API payloads into Jarvis Contact entities."""

from jarvis.core.contacts.contact import contact_id_for_name, new_contact


class GoogleContactsMapper:
    """Convert Google People API records to Contact objects."""

    def to_contact(self, person):
        """Return one Contact from a People API person resource."""
        data = dict(person or {})
        resource_name = str(data.get("resourceName") or "")
        display_name = first_display_name(data) or first_email(data) or first_phone(data) or "Google 연락처"
        aliases = tuple(alias for alias in [display_name, first_given_name(data), first_family_name(data)] if alias)
        return new_contact(
            display_name,
            id=contact_id_for_name(display_name),
            aliases=aliases,
            emails=tuple(extract_values(data.get("emailAddresses"), "value")),
            phones=tuple(extract_values(data.get("phoneNumbers"), "value")),
            birthday=first_birthday(data),
            source="google_contacts",
            confidence=0.98,
            verified=True,
            metadata={
                "provider": "google_contacts",
                "external_id": resource_name,
                "google_resource_name": resource_name,
                "google_etag": str(data.get("etag") or ""),
            },
        )

    def list_to_contacts(self, response):
        """Return contacts from searchContacts or connections.list response."""
        data = dict(response or {})
        raw_contacts = []

        if "results" in data:
            raw_contacts = [item.get("person") for item in data.get("results") or []]
        elif "connections" in data:
            raw_contacts = list(data.get("connections") or [])

        return tuple(self.to_contact(person) for person in raw_contacts if isinstance(person, dict))


def first_display_name(data):
    """Return the first display name."""
    for item in data.get("names") or []:
        value = str(item.get("displayName") or "").strip()
        if value:
            return value
    return ""


def first_given_name(data):
    """Return the first given name."""
    for item in data.get("names") or []:
        value = str(item.get("givenName") or "").strip()
        if value:
            return value
    return ""


def first_family_name(data):
    """Return the first family name."""
    for item in data.get("names") or []:
        value = str(item.get("familyName") or "").strip()
        if value:
            return value
    return ""


def first_email(data):
    """Return first email value."""
    values = extract_values(data.get("emailAddresses"), "value")
    return values[0] if values else ""


def first_phone(data):
    """Return first phone value."""
    values = extract_values(data.get("phoneNumbers"), "value")
    return values[0] if values else ""


def extract_values(items, key):
    """Return non-empty values from a list of Google field dictionaries."""
    values = []

    for item in items or []:
        value = str(dict(item or {}).get(key) or "").strip()
        if value and value not in values:
            values.append(value)

    return values


def first_birthday(data):
    """Return first birthday as MM-DD or YYYY-MM-DD."""
    for item in data.get("birthdays") or []:
        birthday_date = dict(item or {}).get("date") or {}
        month = birthday_date.get("month")
        day = birthday_date.get("day")
        year = birthday_date.get("year")

        if not month or not day:
            continue

        if year:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

        return f"{int(month):02d}-{int(day):02d}"

    return ""
