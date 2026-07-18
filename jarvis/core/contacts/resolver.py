"""Contact command parsing and graph integration."""

from dataclasses import dataclass, field
import re

from jarvis.core.contacts.repository import ContactRepository
from jarvis.voice.semantic.graph import (
    EDGE_ALIAS,
    EDGE_BIRTHDAY,
    EDGE_COMPANY,
    EDGE_COUNTRY,
    EDGE_EMAIL,
    EDGE_LANGUAGE,
    EDGE_PHONE,
    EDGE_RELATIONSHIP,
    EDGE_TAG,
    EDGE_TIMEZONE,
    EDGE_WORKS_AT,
    EntityEdge,
    EntityNode,
    NODE_EMAIL,
    NODE_PERSON,
    NODE_PHONE,
)


@dataclass(frozen=True)
class ContactCommand:
    """A parsed contact command."""

    action: str
    name: str = ""
    attribute: str = ""
    value: str = ""
    raw_text: str = ""
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)


class ContactCommandParser:
    """Parse Korean contact memory commands."""

    def parse(self, text):
        """Return a contact command or an unknown command."""
        raw_text = str(text or "").strip()
        normalized = normalize_text(raw_text)

        command = parse_store_contact(normalized)
        if command is not None:
            return command

        command = parse_email(normalized)
        if command is not None:
            return command

        command = parse_phone(normalized)
        if command is not None:
            return command

        command = parse_birthday(normalized)
        if command is not None:
            return command

        command = parse_recall(normalized)
        if command is not None:
            return command

        return ContactCommand(action="unknown", raw_text=raw_text, confidence=0.0)


class ContactResolver:
    """High-level contact command executor."""

    def __init__(self, repository=None, parser=None, entity_graph=None):
        """Create a resolver."""
        self.repository = repository or ContactRepository()
        self.parser = parser or ContactCommandParser()
        self.entity_graph = entity_graph

    def handle(self, text):
        """Parse and apply a contact command."""
        command = self.parser.parse(text)

        if command.action == "store":
            contact = self.repository.ensure(command.name)
            self.sync_graph(contact)
            return ContactCommandResult(command=command, contact=contact, success=True, message=f"{contact.display_name} 연락처를 저장했습니다.")

        if command.action == "update":
            contact = self.apply_update(command)
            self.sync_graph(contact)
            return ContactCommandResult(command=command, contact=contact, success=True, message=format_update_message(contact, command))

        if command.action == "recall":
            contact = self.repository.resolve(command.name)
            if contact is None:
                return ContactCommandResult(command=command, success=False, found=False, message="연락처를 찾지 못했습니다.")
            self.sync_graph(contact)
            return ContactCommandResult(command=command, contact=contact, success=True, found=True, message=format_recall_message(contact, command.attribute))

        return ContactCommandResult(command=command, success=False, message="연락처 명령을 이해하지 못했습니다.")

    def apply_update(self, command):
        """Apply one parsed update."""
        if command.attribute == "email":
            return self.repository.update_email(command.name, command.value)
        if command.attribute == "phone":
            return self.repository.update_phone(command.name, command.value)
        if command.attribute == "birthday":
            return self.repository.update_birthday(command.name, command.value)
        return self.repository.ensure(command.name)

    def sync_graph(self, contact):
        """Attach contact facts to the entity graph when present."""
        if self.entity_graph is None or contact is None:
            return None
        return sync_contact_to_graph(self.entity_graph, contact)


@dataclass(frozen=True)
class ContactCommandResult:
    """Result of executing a contact command."""

    command: ContactCommand
    contact: object = None
    success: bool = False
    found: bool = False
    message: str = ""


def sync_contact_to_graph(graph, contact):
    """Add one contact and its properties to an EntityGraph."""
    remove_contact_property_edges(graph, contact.id)
    person = graph.add_node(
        EntityNode(
            id=contact.id,
            type=NODE_PERSON,
            name=contact.display_name,
            aliases=contact.aliases,
            sources=("contacts",),
            confidence_by_source={"contacts": contact.confidence},
            revision=contact.revision,
            source=contact.source,
            verified=contact.verified,
        )
    )

    for alias in contact.aliases:
        if alias != contact.display_name:
            graph.add_edge(contact_edge(person.id, EDGE_ALIAS, contact, value=alias))

    for email in contact.emails:
        email_id = f"email_{safe_entity_id(email)}"
        graph.add_node(EntityNode(id=email_id, type=NODE_EMAIL, name=email, aliases=(email,), sources=("contacts",)))
        graph.add_edge(contact_edge(person.id, EDGE_EMAIL, contact, target_id=email_id))

    for phone in contact.phones:
        phone_id = f"phone_{safe_entity_id(phone)}"
        graph.add_node(EntityNode(id=phone_id, type=NODE_PHONE, name=phone, aliases=(phone,), sources=("contacts",)))
        graph.add_edge(contact_edge(person.id, EDGE_PHONE, contact, target_id=phone_id))

    if contact.birthday:
        graph.add_edge(contact_edge(person.id, EDGE_BIRTHDAY, contact, value=contact.birthday))

    if contact.country:
        graph.add_edge(contact_edge(person.id, EDGE_COUNTRY, contact, value=contact.country))

    if contact.language:
        graph.add_edge(contact_edge(person.id, EDGE_LANGUAGE, contact, value=contact.language))

    if contact.timezone:
        graph.add_edge(contact_edge(person.id, EDGE_TIMEZONE, contact, value=contact.timezone))

    for tag in contact.tags:
        graph.add_edge(contact_edge(person.id, EDGE_TAG, contact, value=tag))

    relationship = str(contact.metadata.get("relationship") or "")
    if relationship:
        graph.add_edge(contact_edge(person.id, EDGE_RELATIONSHIP, contact, value=relationship))

    works_at = str(contact.metadata.get("works_at") or contact.metadata.get("company") or "")
    if works_at:
        graph.add_edge(contact_edge(person.id, EDGE_WORKS_AT, contact, value=works_at))
        graph.add_edge(contact_edge(person.id, EDGE_COMPANY, contact, value=works_at))

    return person


def contact_edge(source_id, edge_type, contact, target_id="", value=None):
    """Create a contact-provenance graph edge."""
    return EntityEdge(
        source_id=source_id,
        type=edge_type,
        target_id=target_id,
        value=value,
        source="contacts",
        confidence=contact.confidence,
        revision=contact.revision,
        verified=contact.verified,
    )


def remove_contact_property_edges(graph, contact_id):
    """Remove property edges owned by contact sync before re-patching."""
    for edge_type in [
        EDGE_ALIAS,
        EDGE_EMAIL,
        EDGE_PHONE,
        EDGE_BIRTHDAY,
        EDGE_COUNTRY,
        EDGE_LANGUAGE,
        EDGE_TIMEZONE,
        EDGE_TAG,
        EDGE_RELATIONSHIP,
        EDGE_WORKS_AT,
        EDGE_COMPANY,
    ]:
        graph.remove_edge(contact_id, edge_type)


def parse_store_contact(text):
    """Parse 'store this person as a contact'."""
    match = re.search(r"(?P<name>[가-힣A-Za-zぁ-んァ-ン一-龥]+?)(?:를|을)?\s*연락처(?:에)?\s*(?:저장|등록)", text)
    if not match:
        return None
    return ContactCommand(action="store", name=match.group("name"), raw_text=text, confidence=0.95)


def parse_email(text):
    """Parse email update or recall."""
    email_match = re.search(r"(?P<email>[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})", text)
    name = extract_name_before_attribute(text, "이메일")

    if email_match and name:
        return ContactCommand(action="update", name=name, attribute="email", value=email_match.group("email"), raw_text=text, confidence=0.96)

    if name and is_recall_text(text):
        return ContactCommand(action="recall", name=name, attribute="email", raw_text=text, confidence=0.9)

    return None


def parse_phone(text):
    """Parse phone update or recall."""
    name = extract_name_before_attribute(text, "전화번호")
    phone_match = re.search(r"(?P<phone>(?:\+?\d[\d -]{7,}\d))", text)

    if phone_match and name:
        return ContactCommand(action="update", name=name, attribute="phone", value=normalize_phone(phone_match.group("phone")), raw_text=text, confidence=0.94)

    if name and is_recall_text(text):
        return ContactCommand(action="recall", name=name, attribute="phone", raw_text=text, confidence=0.88)

    return None


def parse_birthday(text):
    """Parse birthday update or recall."""
    name = extract_name_before_attribute(text, "생일")
    birthday = extract_birthday_value(text)

    if birthday and name and not is_recall_text(text):
        return ContactCommand(action="update", name=name, attribute="birthday", value=birthday, raw_text=text, confidence=0.96)

    if name and ("생일" in text) and is_recall_text(text):
        return ContactCommand(action="recall", name=name, attribute="birthday", raw_text=text, confidence=0.9)

    return None


def parse_recall(text):
    """Parse general contact recall."""
    match = re.search(r"(?P<name>[가-힣A-Za-zぁ-んァ-ン一-龥]+)\s*연락처\s*(?:알려|뭐|조회|보여)", text)
    if match:
        return ContactCommand(action="recall", name=match.group("name"), attribute="contact", raw_text=text, confidence=0.9)
    return None


def extract_name_before_attribute(text, attribute):
    """Return the token before an attribute name."""
    match = re.search(rf"(?P<name>[가-힣A-Za-zぁ-んァ-ン一-龥]+)\s*{attribute}", text)
    return match.group("name") if match else ""


def extract_birthday_value(text):
    """Return YYYY-MM-DD or MM-DD for a Korean birthday phrase."""
    full = re.search(r"(?P<year>\d{4})\s*년\s*(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일", text)
    if full:
        return f"{int(full.group('year')):04d}-{int(full.group('month')):02d}-{int(full.group('day')):02d}"

    month_day = re.search(r"(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일", text)
    if month_day:
        return f"{int(month_day.group('month')):02d}-{int(month_day.group('day')):02d}"

    iso = re.search(r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})", text)
    if iso:
        return f"{int(iso.group('year')):04d}-{int(iso.group('month')):02d}-{int(iso.group('day')):02d}"

    return ""


def is_recall_text(text):
    """Return whether text asks for a stored value."""
    return any(token in text for token in ["알려", "뭐", "뭐야", "언제", "언제야", "조회", "보여"])


def normalize_phone(value):
    """Normalize phone number spacing."""
    return re.sub(r"\s+", "", str(value or "").strip())


def normalize_text(text):
    """Normalize whitespace."""
    return " ".join(str(text or "").strip().split())


def format_update_message(contact, command):
    """Return a Korean update message."""
    if command.attribute == "email":
        return f"{contact.display_name} 이메일을 저장했습니다."
    if command.attribute == "phone":
        return f"{contact.display_name} 전화번호를 저장했습니다."
    if command.attribute == "birthday":
        return f"{contact.display_name} 생일을 저장했습니다."
    return f"{contact.display_name} 연락처를 저장했습니다."


def format_recall_message(contact, attribute):
    """Return a Korean recall message."""
    if attribute == "email":
        return f"{contact.display_name} 이메일은 {', '.join(contact.emails) if contact.emails else '저장되어 있지 않습니다'}."
    if attribute == "phone":
        return f"{contact.display_name} 전화번호는 {', '.join(contact.phones) if contact.phones else '저장되어 있지 않습니다'}."
    if attribute == "birthday":
        return f"{contact.display_name} 생일은 {format_birthday(contact.birthday) if contact.birthday else '저장되어 있지 않습니다'}."

    parts = [f"이름: {contact.display_name}"]
    if contact.emails:
        parts.append(f"이메일: {', '.join(contact.emails)}")
    if contact.phones:
        parts.append(f"전화번호: {', '.join(contact.phones)}")
    if contact.birthday:
        parts.append(f"생일: {format_birthday(contact.birthday)}")
    if contact.notes:
        parts.append(f"메모: {contact.notes}")
    return " / ".join(parts)


def format_birthday(value):
    """Return a natural birthday string."""
    text = str(value or "")
    if re.match(r"^\d{2}-\d{2}$", text):
        month, day = text.split("-", 1)
        return f"{int(month)}월 {int(day)}일"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        year, month, day = text.split("-")
        return f"{int(year)}년 {int(month)}월 {int(day)}일"
    return text


def safe_entity_id(value):
    """Return a graph-safe ID fragment."""
    return re.sub(r"[^\w가-힣_-]", "_", str(value or "").lower()).strip("_") or "value"
