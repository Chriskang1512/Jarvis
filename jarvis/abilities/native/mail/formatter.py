"""Korean formatter for Mail Ability results."""

from datetime import datetime


def format_mail_result(result):
    """Format one structured MailResult for TTS."""
    if result.user_message:
        return result.user_message

    if not result.success:
        return error_message(result)

    if result.action in {"list", "search"}:
        return list_message(result.messages, result.query)

    if result.action == "get":
        return get_message(result.message, include_body=True)

    if result.action in {"send", "reply"} and result.requires_confirmation:
        return outgoing_preview(result.outgoing)

    return "메일 요청을 처리했습니다."


def outgoing_preview(outgoing):
    """Return the exact draft preview shown before confirmation."""
    if outgoing is None:
        return "메일 내용을 확인하지 못했습니다."
    recipient = clean_sender(outgoing.recipient_name) or masked_recipient(outgoing.to[0] if outgoing.to else "")
    action = "답장" if outgoing.reply_to_message_id else "메일"
    return (
        f"{recipient}에게 '{outgoing.subject}'라는 제목의 {action}을 보낼까요? "
        f"내용은 '{outgoing.body}'입니다."
    )


def format_mail_send_result(result):
    """Return a safe send/reply result."""
    if result.user_message:
        return result.user_message
    if not result.success:
        return send_error_message(result)
    recipient = clean_sender(result.recipient_name) or masked_recipient(result.recipient)
    if result.action == "reply":
        return f"{recipient}에게 답장을 보냈습니다. 제목은 '{result.subject}'입니다."
    return f"{recipient}에게 메일을 보냈습니다. 제목은 '{result.subject}'입니다."


def send_error_message(result):
    """Return a user-facing stable send failure."""
    code = str(result.error_code or "")
    messages = {
        "RECIPIENT_NOT_FOUND": "메일을 보낼 수신자를 찾지 못했습니다.",
        "RECIPIENT_EMAIL_MISSING": f"{result.recipient_name or '해당'} 연락처에 이메일 주소가 없습니다.",
        "AMBIGUOUS_RECIPIENT": "동명이인 연락처가 여러 개 있습니다. 수신자를 더 정확히 말씀해 주세요.",
        "INVALID_EMAIL_ADDRESS": "이메일 주소 형식이 올바르지 않습니다.",
        "MAIL_BODY_REQUIRED": "메일 본문이 필요합니다.",
        "MAIL_SUBJECT_REQUIRED": "메일 제목이 필요합니다.",
        "SEND_CONFIRMATION_REQUIRED": "메일 전송 전에 확인이 필요합니다.",
        "SEND_FAILED": "메일 전송에 실패했습니다.",
        "REPLY_TARGET_NOT_FOUND": "어떤 메일에 답장할지 먼저 선택해 주세요.",
        "DUPLICATE_SEND_BLOCKED": "같은 메일의 중복 전송을 차단했습니다.",
    }
    return messages.get(code, error_message(result))


def masked_recipient(value):
    """Mask an email address for spoken previews without a contact name."""
    text = str(value or "")
    if "@" not in text:
        return text or "수신자"
    local, domain = text.split("@", 1)
    return f"{local[:1]}***@{domain}"


def list_message(messages, query=""):
    """Return compact mail list text."""
    items = list(messages or ())
    prefix = "최근 메일"

    if query:
        if "is:unread" in query:
            prefix = "안 읽은 메일"
        elif "newer_than:1d" in query:
            prefix = "오늘 온 메일"

    if len(items) == 0:
        return f"{prefix}은 없습니다."

    lines = [f"{prefix}은 {len(items)}건입니다."]

    for index, message in enumerate(items, start=1):
        sender = clean_sender(message.sender_name or message.sender_email or "보낸 사람 없음")
        subject = message.subject or "제목 없음"
        received = format_received_at(message.received_at)
        suffix = f" {received}." if received else ""
        lines.append(f"{index}. {sender}. {subject}.{suffix}")

    lines.append("읽고 싶은 메일 번호를 말씀해 주세요.")
    return "\n".join(lines)


def get_message(message, include_body=False):
    """Return one message summary."""
    if message is None:
        return "메일을 찾지 못했습니다."

    sender = clean_sender(message.sender_name or message.sender_email or "보낸 사람 없음")
    subject = message.subject or "제목 없음"
    snippet = message.body_summary or message.snippet
    received = format_received_at(message.received_at)
    received_sentence = f" 받은 시각은 {received}입니다." if received else ""

    if include_body and snippet:
        return f"{sender}의 메일입니다. 제목은 {subject}입니다.{received_sentence} 요약은 {snippet}. 답장하시겠습니까?"

    return f"{sender}의 메일입니다. 제목은 {subject}입니다.{received_sentence}"


def format_received_at(value):
    """Format Gmail internalDate milliseconds for Korean speech."""
    text = str(value or "").strip()

    if not text:
        return ""

    try:
        timestamp = int(text) / 1000
        received = datetime.fromtimestamp(timestamp)
    except (TypeError, ValueError, OSError):
        return ""

    today = datetime.now().date()
    day_prefix = "오늘" if received.date() == today else f"{received.month}월 {received.day}일"
    period = "오전" if received.hour < 12 else "오후"
    hour = received.hour % 12 or 12
    return f"{day_prefix} {period} {hour}시"


def clean_sender(value):
    """Remove whitespace and a stray trailing comma from sender display names."""
    return str(value or "").strip().rstrip(",，").strip()


def error_message(result):
    """Return user-facing error text."""
    code = str(result.error_code or "")

    if code == "MAIL_NOT_FOUND":
        return "메일을 찾지 못했습니다."
    if code == "AUTH_REQUIRED":
        return "Gmail 인증이 필요합니다."
    if code == "SCOPE_INSUFFICIENT":
        return "Gmail 읽기 권한이 없습니다."
    if code == "FEATURE_NOT_ENABLED":
        return "Google Cloud에서 Gmail API를 활성화해야 합니다."
    if code in {"PERMISSION_DENIED", "AUTH_EXPIRED", "AUTH_REFRESH_FAILED"}:
        return "Gmail 권한을 확인해야 합니다."
    if code in {"PROVIDER_TIMEOUT", "PROVIDER_UNAVAILABLE", "RATE_LIMITED"}:
        return "Gmail 서비스를 지금 사용할 수 없습니다."

    return "메일 요청을 처리하지 못했습니다."
