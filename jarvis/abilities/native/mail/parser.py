"""Mail intent parser."""

import re
from dataclasses import replace

from jarvis.abilities.native.mail.query import MailQuery


def normalize_query(input_data, parser=None):
    """Return MailQuery from dict/object/text."""
    if hasattr(input_data, "action") and hasattr(input_data, "query"):
        return input_data

    parser = parser or MailIntentParser()

    if isinstance(input_data, dict) and "action" in input_data:
        raw_text = str(input_data.get("raw_text", input_data.get("text", "")) or "")
        query = MailQuery(
            action=str(input_data.get("action", "list") or "list"),
            query=str(input_data.get("query", "") or ""),
            sender=str(input_data.get("sender", "") or input_data.get("from", "") or ""),
            label=str(input_data.get("label", "") or ""),
            unread=bool(input_data.get("unread", False)),
            today=bool(input_data.get("today", False)),
            limit=int(input_data.get("limit", 5) or 5),
            message_id=str(input_data.get("message_id", "") or ""),
            thread_id=str(input_data.get("thread_id", "") or ""),
            ordinal=int(input_data.get("ordinal", 0) or 0),
            include_body=bool(input_data.get("include_body", False)),
            recipient=str(input_data.get("recipient", "") or ""),
            recipient_name=str(input_data.get("recipient_name", "") or ""),
            to=tuple(input_data.get("to", ()) or ()),
            cc=tuple(input_data.get("cc", ()) or ()),
            bcc=tuple(input_data.get("bcc", ()) or ()),
            subject=str(input_data.get("subject", "") or ""),
            body=str(input_data.get("body", "") or ""),
            reply_to_message_id=str(input_data.get("reply_to_message_id", "") or ""),
            reply_to_header=str(input_data.get("reply_to_header", "") or ""),
            pending_action_id=str(input_data.get("pending_action_id", "") or ""),
            confirmed=bool(input_data.get("_confirmed", input_data.get("confirmed", False))),
            raw_text=raw_text,
        )
        if raw_text:
            parsed = parser.parse(raw_text)
            return merge_query(query, parsed)
        return query

    raw_text = input_data.get("text", "") if isinstance(input_data, dict) else str(input_data or "")
    return parser.parse(raw_text)


class MailIntentParser:
    """Parse Korean Gmail read commands."""

    def parse(self, text):
        """Return MailQuery."""
        raw_text = str(text or "").strip()
        normalized = " ".join(raw_text.split())
        normalized = correct_mail_stt_variant(normalized)

        if is_reply_command(normalized):
            return parse_compose_query(normalized, raw_text, action="reply")

        if is_send_command(normalized):
            return parse_compose_query(normalized, raw_text, action="send")

        ordinal = parse_ordinal(normalized)
        if ordinal:
            return MailQuery(action="get", ordinal=ordinal, include_body=True, raw_text=raw_text)

        query = build_gmail_query(normalized)
        action = "search" if query else "list"
        return MailQuery(
            action=action,
            query=query,
            unread="안 읽" in normalized or "읽지 않은" in normalized,
            today="오늘" in normalized,
            limit=parse_limit(normalized),
            raw_text=raw_text,
        )


def merge_query(primary, parsed):
    """Fill missing structured fields from parsed raw text."""
    query = primary.query or parsed.query
    action = primary.action or parsed.action

    if primary.action in {"list", "search"} and query:
        action = "search"

    return replace(
        primary,
        action=action,
        query=query,
        unread=primary.unread or parsed.unread,
        today=primary.today or parsed.today,
        ordinal=primary.ordinal or parsed.ordinal,
        include_body=primary.include_body or parsed.include_body,
        limit=primary.limit or parsed.limit,
        recipient=primary.recipient or parsed.recipient,
        recipient_name=primary.recipient_name or parsed.recipient_name,
        to=primary.to or parsed.to,
        cc=primary.cc or parsed.cc,
        bcc=primary.bcc or parsed.bcc,
        subject=primary.subject or parsed.subject,
        body=primary.body or parsed.body,
        message_id=primary.message_id or parsed.message_id,
        thread_id=primary.thread_id or parsed.thread_id,
        reply_to_message_id=primary.reply_to_message_id or parsed.reply_to_message_id,
        reply_to_header=primary.reply_to_header or parsed.reply_to_header,
        pending_action_id=primary.pending_action_id or parsed.pending_action_id,
    )


EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
    r"(?![A-Za-z0-9._%+-])"
)


def is_send_command(text):
    """Return whether text asks to compose a new message."""
    value = str(text or "")
    return any(token in value for token in ["메일", "이메일"]) and any(
        token in value for token in ["보내줘", "보내 줘", "보내", "전송해", "전송해줘"]
    )


def is_reply_command(text):
    """Return whether text asks to reply to a message."""
    value = str(text or "")
    return "답장" in value and any(token in value for token in ["해줘", "해 줘", "보내", "작성", "답장"])


def parse_compose_query(text, raw_text="", action="send"):
    """Parse a deterministic send/reply draft request."""
    normalized = " ".join(str(text or "").split()).strip()
    email_match = EMAIL_PATTERN.search(normalized)
    recipient = email_match.group(1) if email_match else parse_recipient_name(normalized)
    explicit_subject, explicit_body = parse_explicit_subject_body(normalized)
    body = explicit_body or parse_compose_body(normalized, recipient, action=action)
    subject = explicit_subject or generate_subject(body, action=action)
    ordinal = parse_ordinal(normalized) if action == "reply" else 0

    return MailQuery(
        action=action,
        recipient=recipient if not email_match else email_match.group(1),
        recipient_name="" if email_match else recipient,
        to=(email_match.group(1),) if email_match else (),
        subject=subject,
        body=body,
        ordinal=ordinal,
        raw_text=raw_text or normalized,
    )


def parse_recipient_name(text):
    """Return the explicitly addressed contact name."""
    match = re.search(r"^\s*(.+?)\s*(?:에게|한테|으로|로)\s+", str(text or ""))
    if not match:
        return ""

    candidate = match.group(1).strip(" '\"")
    if EMAIL_PATTERN.fullmatch(candidate):
        return candidate
    return candidate


def parse_explicit_subject_body(text):
    """Return explicit Korean subject/body clauses when present."""
    value = str(text or "")
    subject_match = re.search(r"제목(?:은|을|:)\s*['\"]?(.+?)['\"]?(?:\s*,?\s*내용(?:은|을|:)|\s+본문(?:은|을|:))", value)
    body_match = re.search(r"(?:내용|본문)(?:은|을|:)\s*['\"]?(.+?)['\"]?\s*(?:메일|이메일)?\s*(?:보내|전송)", value)
    return (
        subject_match.group(1).strip(" '\".,") if subject_match else "",
        normalize_body(body_match.group(1)) if body_match else "",
    )


def parse_compose_body(text, recipient="", action="send"):
    """Extract the requested message body without inventing recipient data."""
    value = str(text or "").strip()

    if action == "reply":
        value = re.sub(r"^(?:첫\s*번째|두\s*번째|세\s*번째|\d+\s*번째|방금\s*읽은|그)\s*메일(?:에|에게)?\s*", "", value)
        value = re.sub(r"\s*답장(?:해줘|해\s*줘|을?\s*보내줘|을?\s*보내\s*줘|해)?\s*$", "", value)
    else:
        if recipient:
            value = re.sub(rf"^\s*{re.escape(recipient)}\s*(?:에게|한테|으로|로)\s*", "", value, count=1)
        value = EMAIL_PATTERN.sub("", value, count=1).strip()
        value = re.sub(r"^(?:에게|한테|으로|로)\s*", "", value)
        value = re.sub(r"\s*(?:메일|이메일)\s*(?:보내줘|보내\s*줘|보내|전송해줘|전송해\s*줘|전송해)\s*$", "", value)

    value = re.sub(r"^(?:내용은|본문은)\s*", "", value)
    return normalize_body(value)


def normalize_body(value):
    """Normalize common Korean quotative compose wording."""
    text = str(value or "").strip(" '\".,")

    replacements = [
        (r"확인했다고$", "확인했습니다"),
        (r"취소됐다고$", "취소됐습니다"),
        (r"취소되었다고$", "취소되었습니다"),
        (r"만나자고$", "만나요"),
        (r"라고$", ""),
        (r"다고$", ""),
    ]
    for pattern, replacement in replacements:
        if re.search(pattern, text):
            text = re.sub(pattern, replacement, text)
            break

    if text == "테스트":
        text = "테스트 메일입니다"
    if text and text[-1] not in ".!?":
        text += "."
    return text


def generate_subject(body, action="send"):
    """Generate a short predictable subject."""
    text = str(body or "")
    if action == "reply":
        return ""
    if "테스트" in text:
        return "테스트 메일"
    if "취소" in text:
        return "일정 취소 안내"
    if any(token in text for token in ["내일", "오늘", "오후", "오전", "시에", "만나"]):
        return "일정 안내" if "내일" not in text else "내일 일정 안내"
    return "안내 메일"


def build_gmail_query(text):
    """Build a safe Gmail search query from a natural phrase."""
    parts = []
    normalized = str(text or "")

    if "안 읽" in normalized or "읽지 않은" in normalized:
        parts.append("is:unread")

    if "오늘" in normalized:
        parts.append("newer_than:1d")

    sender = parse_sender_hint(normalized)
    if sender:
        parts.append(f"from:{sender}")

    keyword = parse_keyword_query(normalized)
    if keyword:
        parts.append(keyword)

    return " ".join(parts)


def correct_mail_stt_variant(text):
    """Return conservative corrections for common Gmail STT variants."""
    normalized = " ".join(str(text or "").split()).strip()

    if not any(token in normalized for token in ["알려", "보여", "조회", "검색", "찾아"]):
        return normalized

    if any(token in normalized for token in ["메일", "이메일"]):
        return normalized

    if re.search(r"^최근\s+일\s*(?:알려|보여|조회|검색|찾아)", normalized):
        return normalized.replace("최근 일", "최근 메일", 1)

    match = re.match(r"^(.+?)\s+매일\s*(알려|보여|조회|검색|찾아)(.*)$", normalized)
    if match and match.group(1).strip():
        return f"{match.group(1).strip()} 메일 {match.group(2)}{match.group(3)}".strip()

    return normalized


def parse_keyword_query(text):
    """Return a preserved natural-language keyword for generic mail searches."""
    normalized = " ".join(str(text or "").split()).strip()

    if not any(token in normalized for token in ["메일", "이메일"]):
        return ""

    list_only_tokens = ["최근", "목록", "전체", "받은", "온 메일"]
    body_tokens = ["본문", "내용", "읽어"]
    special_search_tokens = ["안 읽", "읽지 않은", "오늘", "github", "GitHub", "openai", "OpenAI", "google", "Google", "깃허브", "구글"]

    if any(token in normalized for token in list_only_tokens + body_tokens + special_search_tokens):
        return ""

    cleaned = normalized
    replacements = [
        "메일",
        "이메일",
        "알려줘",
        "알려 줘",
        "보여줘",
        "보여 줘",
        "찾아줘",
        "찾아 줘",
        "검색해줘",
        "검색해 줘",
        "조회해줘",
        "조회해 줘",
        "관련",
        "좀",
    ]

    for token in replacements:
        cleaned = cleaned.replace(token, " ")

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .?。")
    return cleaned


def parse_sender_hint(text):
    """Return a simple from: query hint."""
    lowered = str(text or "").lower()

    known = {
        "github": "github",
        "깃허브": "github",
        "openai": "openai",
        "오픈ai": "openai",
        "오픈 AI": "openai",
        "google": "google",
        "구글": "google",
    }

    for token, sender in known.items():
        if token.lower() in lowered:
            return sender

    match = re.search(r"([A-Za-z0-9_.+-]+@[A-Za-z0-9_.-]+)\s*(?:메일|이메일)", text)
    if match:
        return match.group(1)

    return ""


def parse_limit(text):
    """Return message list limit."""
    match = re.search(r"(\d+)\s*건", str(text or ""))
    if match:
        return max(1, min(int(match.group(1)), 10))
    return 5


def parse_ordinal(text):
    """Return one-based ordinal for follow-up reads."""
    value = str(text or "")

    match = re.search(r"(\d+)\s*번", value)
    if match:
        return int(match.group(1))

    if "첫 번째" in value or "첫번째" in value:
        return 1
    if "두 번째" in value or "두번째" in value:
        return 2
    if "세 번째" in value or "세번째" in value:
        return 3

    return 0
