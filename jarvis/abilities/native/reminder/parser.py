import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from jarvis.date_calculator import today
from jarvis.debug_trace import trace_event


@dataclass(frozen=True)
class ReminderQuery:
    """Normalized reminder query."""

    action: str = "create"
    title: str = ""
    datetime: str = ""
    remind_before: int | None = 30
    raw_text: str = ""
    recurrence: str = ""
    snooze_until: str = ""
    priority: str = "normal"
    reminder_id: str = ""
    calendar_id: str = ""


class ReminderIntentParser:
    """Parse Korean reminder requests."""

    def parse(self, text):
        """Return ReminderQuery."""
        return parse_reminder_intent(text)


def parse_reminder_intent(text):
    """Parse text into a reminder query."""
    raw_text = str(text or "").strip()
    normalized = " ".join(raw_text.split())
    action = detect_action(normalized)
    relative_delay = detect_relative_delay_minutes(normalized)
    remind_before = 0 if relative_delay is not None else detect_remind_before(normalized)
    date_value = detect_date(normalized)
    time_value = detect_time(normalized)
    datetime_value = f"{date_value}T{time_value}"

    if relative_delay is not None:
        datetime_value = (datetime.now() + timedelta(minutes=relative_delay)).isoformat(timespec="seconds")

    title = extract_title(normalized, action)
    recurrence = detect_recurrence(normalized)
    priority = detect_priority(normalized)
    trace_event(
        "reminder.parser",
        raw=raw_text,
        matched_pattern=detect_matched_pattern(normalized, relative_delay),
        time=f"{relative_delay}m" if relative_delay is not None else "",
        title=title,
    )

    return ReminderQuery(
        action=action,
        title=title,
        datetime=datetime_value,
        remind_before=remind_before,
        raw_text=raw_text,
        recurrence=recurrence,
        priority=priority,
    )


def detect_matched_pattern(text, relative_delay):
    """Return a trace-friendly parser pattern name."""
    if relative_delay is not None and re.search(r"(알려\s*줘|알려줘|해\s*줘|해줘)", text):
        return "relative_tell_me"

    if relative_delay is not None:
        return "relative_alarm"

    return "default"


def detect_action(text):
    """Detect reminder action."""
    if contains_any(text, ["알림 끄기", "알림 취소", "취소", "끄기"]):
        return "cancel"

    if contains_any(text, ["알림 목록", "알림 뭐", "알림 알려", "리마인더 목록"]):
        return "list"

    return "create"


def detect_remind_before(text):
    """Detect remind-before minutes."""
    hour_match = re.search(r"(\d+)\s*시간\s*전", text)

    if hour_match:
        return int(hour_match.group(1)) * 60

    minute_match = re.search(r"(\d+)\s*분\s*전", text)

    if minute_match:
        return int(minute_match.group(1))

    return 30


def detect_relative_delay_minutes(text):
    """Detect relative alarm delay, such as '1분 뒤' or '2시간 후'."""
    hour_match = re.search(r"(\d+)\s*시간\s*(뒤|후)", text)

    if hour_match:
        return int(hour_match.group(1)) * 60

    minute_match = re.search(r"(\d+)\s*분\s*(뒤|후)", text)

    if minute_match:
        return int(minute_match.group(1))

    return None


def detect_date(text):
    """Detect reminder date."""
    if "모레" in text:
        return (date.fromisoformat(today()) + timedelta(days=2)).isoformat()

    if "내일" in text:
        return (date.fromisoformat(today()) + timedelta(days=1)).isoformat()

    if "다음주" in text or "다음 주" in text:
        return (date.fromisoformat(today()) + timedelta(days=7)).isoformat()

    if "오늘" in text:
        return today()

    iso_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)

    if iso_match:
        return iso_match.group(0)

    return today()


def detect_time(text):
    """Detect simple Korean time expressions."""
    match = re.search(r"(오전|오후)?\s*(\d{1,2})\s*시", text)

    if not match:
        return "09:00:00"

    period = match.group(1) or ""
    hour = int(match.group(2))

    if period == "오후" and hour < 12:
        hour += 12

    if period == "오전" and hour == 12:
        hour = 0

    return f"{hour:02d}:00:00"


def detect_recurrence(text):
    """Detect simple recurrence phrase for future scheduler support."""
    if "매일" in text:
        return "daily"

    if "매주" in text:
        return "weekly"

    if "매달" in text or "매월" in text:
        return "monthly"

    if "평일마다" in text or "평일 마다" in text:
        return "weekdays"

    if "주말마다" in text or "주말 마다" in text:
        return "weekends"

    return ""


def detect_priority(text):
    """Detect notification priority."""
    if "긴급" in text:
        return "urgent"

    if "중요" in text:
        return "high"

    if "낮음" in text or "낮게" in text:
        return "low"

    return "normal"


def extract_title(text, action):
    """Extract reminder title."""
    if action != "create":
        return ""

    cleaned = text

    for token in [
        "오늘",
        "내일",
        "모레",
        "다음주",
        "다음 주",
        "오전",
        "오후",
        "뒤에",
        "후에",
        "뒤",
        "후",
        "알람",
        "알림",
        "알려줘",
        "알려 줘",
        "등록해",
        "등록해 줘",
        "추가해",
        "맞춰",
        "맞춰 줘",
        "해 줘",
        "리마인드",
        "리마인더",
    ]:
        cleaned = cleaned.replace(token, " ")

    cleaned = re.sub(r"\d+\s*분\s*전", " ", cleaned)
    cleaned = re.sub(r"\d+\s*시간\s*전", " ", cleaned)
    cleaned = re.sub(r"\d+\s*분\s*(뒤|후)", " ", cleaned)
    cleaned = re.sub(r"\d+\s*시간\s*(뒤|후)", " ", cleaned)
    cleaned = re.sub(r"\d+\s*분", " ", cleaned)
    cleaned = re.sub(r"\d+\s*시간", " ", cleaned)
    cleaned = re.sub(r"\d{1,2}\s*시", " ", cleaned)
    cleaned = re.sub(r"\d{4}-\d{2}-\d{2}", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .?!")
    cleaned = cleaned.removeprefix("에 ").strip()
    cleaned = cleaned.removeprefix("에").strip()
    cleaned = normalize_reminder_title(cleaned)
    return cleaned or default_direct_reminder_title(text)


def normalize_reminder_title(text):
    """Normalize common spoken reminder object phrases."""
    normalized = str(text or "").strip()

    if re.search(r"깨워\s*줘|깨워줘|깨워", normalized):
        return "깨우기"

    replacements = {
        "물 마시게": "물 마시기",
        "물 마시라고": "물 마시기",
        "물 마셔": "물 마시기",
        "물 마시기라고": "물 마시기",
    }

    for source, target in replacements.items():
        normalized = normalized.replace(source, target)

    normalized = re.sub(r"\s*(라고|하라고)\s*$", "", normalized).strip()
    normalized = re.sub(r"\s*(맞춰|등록해|알려줘|알려 줘|해줘|해 줘|알람|알림|줘)\s*$", "", normalized).strip()

    return normalized.strip()


def contains_any(text, tokens):
    """Return whether any token is present."""
    return any(token in text for token in tokens)


def default_direct_reminder_title(text):
    """Return a natural title for direct alarms without an explicit object."""
    if re.search(r"깨워\s*줘|깨워줘|깨워", str(text or "")):
        return "깨우기"

    return "알람"
