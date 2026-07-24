import re

from jarvis.abilities.native.contacts.query import ContactQuery
from jarvis.core.contacts.contact import contact_id_for_name, normalize_contact_name


class ContactIntentParser:
    """Parse Korean Contact Ability commands."""

    def parse(self, text):
        """Return a ContactQuery from free text."""
        raw_text = str(text or "").strip()
        normalized = normalize_text(raw_text)

        query = parse_clean_korean_contact(normalized, raw_text)
        if query is not None:
            return query

        query = parse_delete(normalized, raw_text)
        if query is not None:
            return query

        query = parse_email(normalized, raw_text)
        if query is not None:
            return query

        query = parse_phone(normalized, raw_text)
        if query is not None:
            return query

        query = parse_birthday(normalized, raw_text)
        if query is not None:
            return query

        query = parse_store(normalized, raw_text)
        if query is not None:
            return query

        query = parse_get(normalized, raw_text)
        if query is not None:
            return query

        return ContactQuery(action="get", raw_text=raw_text)


def parse_store(text, raw_text):
    """Parse contact create commands."""
    match = re.search(r"(?P<name>[\w가-힣ぁ-んァ-ン一-龥]+)(?:를|을)?\s*연락처(?:에)?\s*(?:저장|등록)", text)

    if not match:
        return None

    name = clean_name(match.group("name"))
    return ContactQuery(
        action="create",
        display_name=name,
        contact_id=contact_id_for_name(name),
        raw_text=raw_text,
    )


def parse_delete(text, raw_text):
    """Parse contact delete commands."""
    if "삭제" not in text and "지워" not in text:
        return None

    match = re.search(r"(?P<name>[\w가-힣ぁ-んァ-ン一-龥]+)\s*연락처", text)

    if not match:
        return None

    name = clean_name(match.group("name"))
    return ContactQuery(
        action="delete",
        display_name=name,
        contact_id=contact_id_for_name(name),
        raw_text=raw_text,
    )


def parse_email(text, raw_text):
    """Parse email update or recall."""
    email_match = re.search(r"(?P<email>[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})", text)
    name = extract_name_before_token(text, "이메일")

    if email_match and name:
        return ContactQuery(
            action="update",
            display_name=name,
            contact_id=contact_id_for_name(name),
            email=email_match.group("email"),
            attribute="email",
            raw_text=raw_text,
        )

    if name and is_recall_text(text):
        return ContactQuery(
            action="get",
            display_name=name,
            contact_id=contact_id_for_name(name),
            attribute="email",
            raw_text=raw_text,
        )

    return None


def parse_phone(text, raw_text):
    """Parse phone update or recall."""
    name = extract_name_before_token(text, "전화번호")
    phone_match = re.search(r"(?P<phone>(?:\+?\d[\d -]{7,}\d))", text)

    if phone_match and name:
        return ContactQuery(
            action="update",
            display_name=name,
            contact_id=contact_id_for_name(name),
            phone=normalize_phone(phone_match.group("phone")),
            attribute="phone",
            raw_text=raw_text,
        )

    if name and is_recall_text(text):
        return ContactQuery(
            action="get",
            display_name=name,
            contact_id=contact_id_for_name(name),
            attribute="phone",
            raw_text=raw_text,
        )

    return None


def parse_birthday(text, raw_text):
    """Parse birthday update or recall."""
    name = extract_name_before_token(text, "생일")
    birthday = extract_birthday(text)

    if birthday and name and not is_recall_text(text):
        return ContactQuery(
            action="update",
            display_name=name,
            contact_id=contact_id_for_name(name),
            birthday=birthday,
            attribute="birthday",
            raw_text=raw_text,
        )

    if name and "생일" in text and is_recall_text(text):
        return ContactQuery(
            action="get",
            display_name=name,
            contact_id=contact_id_for_name(name),
            attribute="birthday",
            raw_text=raw_text,
        )

    return None


def parse_get(text, raw_text):
    """Parse general contact recall."""
    match = re.search(r"(?P<name>[\w가-힣ぁ-んァ-ン一-龥]+)\s*연락처\s*(?:알려|보여|조회|뭐)", text)

    if not match:
        return None

    name = clean_name(match.group("name"))
    return ContactQuery(
        action="get",
        display_name=name,
        contact_id=contact_id_for_name(name),
        attribute="contact",
        raw_text=raw_text,
    )


def normalize_query(input_data, parser=None):
    """Return ContactQuery from dict, object, or text."""
    if hasattr(input_data, "action") and hasattr(input_data, "display_name"):
        return input_data

    if isinstance(input_data, dict) and "action" in input_data:
        return ContactQuery(
            action=str(input_data.get("action", "get")),
            contact_id=str(input_data.get("contact_id", "")),
            display_name=str(input_data.get("display_name", "")),
            aliases=tuple(input_data.get("aliases", ()) or ()),
            email=str(input_data.get("email", "")),
            phone=str(input_data.get("phone", "")),
            birthday=str(input_data.get("birthday", "")),
            attribute=str(input_data.get("attribute", "contact")),
            external_id=str(input_data.get("external_id", "")),
            source=str(input_data.get("source", "user")),
            confirmed=bool(input_data.get("_confirmed", input_data.get("confirmed", False))),
            raw_text=str(input_data.get("raw_text", "")),
        )

    raw_text = ""
    if isinstance(input_data, dict):
        raw_text = input_data.get("raw_text") or input_data.get("text") or ""
    else:
        raw_text = str(input_data or "")

    parser = parser or ContactIntentParser()
    return parser.parse(raw_text)


def parse_clean_korean_contact(text, raw_text):
    """Parse readable Korean contact read/write commands."""
    query = parse_clean_delete(text, raw_text)
    if query is not None:
        return query

    query = parse_clean_email(text, raw_text)
    if query is not None:
        return query

    query = parse_clean_phone(text, raw_text)
    if query is not None:
        return query

    query = parse_clean_birthday(text, raw_text)
    if query is not None:
        return query

    query = parse_clean_store(text, raw_text)
    if query is not None:
        return query

    return parse_clean_get(text, raw_text)


def parse_clean_store(text, raw_text):
    """Parse contact create commands in readable Korean."""
    match = re.search(r"(?P<name>[\w가-힣]+)(?:를|을)?\s*연락처(?:에)?\s*(?:저장|등록)", text)

    if not match:
        return None

    name = clean_name(match.group("name"))
    return ContactQuery(action="create", display_name=name, contact_id=contact_id_for_name(name), raw_text=raw_text)


def parse_clean_delete(text, raw_text):
    """Parse contact delete commands in readable Korean."""
    if not any(token in text for token in ["삭제", "지워"]):
        return None

    match = re.search(r"(?P<name>[\w가-힣]+)\s*연락처", text)

    if not match:
        return None

    name = clean_name(match.group("name"))
    return ContactQuery(action="delete", display_name=name, contact_id=contact_id_for_name(name), raw_text=raw_text)


def parse_clean_email(text, raw_text):
    """Parse email update or recall in readable Korean."""
    email_match = re.search(r"(?P<email>[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})", text)
    name = extract_clean_name_before_token(text, "이메일")

    if not name:
        name = extract_clean_name_before_token(text, "메일")

    if email_match and name:
        return ContactQuery(
            action="update",
            display_name=name,
            contact_id=contact_id_for_name(name),
            email=email_match.group("email"),
            attribute="email",
            raw_text=raw_text,
        )

    if name and is_clean_recall_text(text):
        return ContactQuery(action="get", display_name=name, contact_id=contact_id_for_name(name), attribute="email", raw_text=raw_text)

    return None


def parse_clean_phone(text, raw_text):
    """Parse phone update or recall in readable Korean."""
    name = extract_clean_name_before_token(text, "전화번호")
    phone_match = re.search(r"(?P<phone>(?:\+?\d[\d -]{7,}\d))", text)

    if phone_match and name:
        return ContactQuery(
            action="update",
            display_name=name,
            contact_id=contact_id_for_name(name),
            phone=normalize_phone(phone_match.group("phone")),
            attribute="phone",
            raw_text=raw_text,
        )

    if name and is_clean_recall_text(text):
        return ContactQuery(action="get", display_name=name, contact_id=contact_id_for_name(name), attribute="phone", raw_text=raw_text)

    return None


def parse_clean_birthday(text, raw_text):
    """Parse birthday update or recall in readable Korean."""
    name = extract_clean_name_before_token(text, "생일")
    birthday = extract_clean_birthday(text)

    if birthday and name and not is_clean_recall_text(text):
        return ContactQuery(
            action="update",
            display_name=name,
            contact_id=contact_id_for_name(name),
            birthday=birthday,
            attribute="birthday",
            raw_text=raw_text,
        )

    if name and "생일" in text and is_clean_recall_text(text):
        return ContactQuery(action="get", display_name=name, contact_id=contact_id_for_name(name), attribute="birthday", raw_text=raw_text)

    return None


def parse_clean_get(text, raw_text):
    """Parse general contact lookup in readable Korean."""
    match = re.search(r"(?P<name>[\w가-힣]+)\s*연락처\s*(?:알려|찾아|보여|조회)", text)

    if not match:
        return None

    name = clean_name(match.group("name"))
    return ContactQuery(action="get", display_name=name, contact_id=contact_id_for_name(name), attribute="contact", raw_text=raw_text)


def extract_clean_name_before_token(text, token):
    """Return a name-like phrase before a clean Korean field token."""
    match = re.search(rf"(?P<name>[\w가-힣]+)\s*{token}", text)
    return clean_name(match.group("name")) if match else ""


def extract_clean_birthday(text):
    """Extract readable Korean birthday as MM-DD or YYYY-MM-DD."""
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


def is_clean_recall_text(text):
    """Return whether readable Korean text asks to retrieve a contact value."""
    return any(token in text for token in ["알려", "찾아", "보여", "조회", "언제", "뭐", "주소"])


def extract_name_before_token(text, token):
    """Return the name-like phrase before a field token."""
    match = re.search(rf"(?P<name>[\w가-힣ぁ-んァ-ン一-龥]+)\s*{token}", text)
    return clean_name(match.group("name")) if match else ""


def extract_birthday(text):
    """Extract birthday as MM-DD or YYYY-MM-DD."""
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
    """Return whether text asks to retrieve a value."""
    return any(token in text for token in ["알려", "뭐", "뭐야", "언제", "언제야", "조회", "보여"])


def clean_name(value):
    """Normalize a contact name phrase."""
    text = normalize_contact_name(value)
    return text.strip("은는이가를을")


def normalize_phone(value):
    """Normalize phone spacing."""
    return re.sub(r"\s+", "", str(value or "").strip())


def normalize_text(text):
    """Normalize whitespace."""
    return " ".join(str(text or "").strip().split())
