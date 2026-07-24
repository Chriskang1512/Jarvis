"""Calendar ability result models and Korean formatter."""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from jarvis.abilities.result import BaseAbilityResult
from jarvis.date_calculator import today


@dataclass(frozen=True)
class CalendarEvent:
    """One normalized calendar event."""

    id: str
    title: str
    date: str
    time: str = ""
    description: str = ""
    location: str = ""
    participants: list[str] = field(default_factory=list)
    reminder_minutes: list[int] = field(default_factory=list)

    def to_dict(self):
        """Return a serializable event dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class CalendarResult(BaseAbilityResult):
    """Calendar Ability result payload."""

    action: str = ""
    events: list[CalendarEvent] = field(default_factory=list)
    count: int = 0
    provider: str = "mock"
    timestamp: str = ""
    message: str = ""
    date: str = ""

    def __post_init__(self):
        """Fill derived defaults."""
        if self.timestamp == "":
            object.__setattr__(self, "timestamp", datetime.now().isoformat(timespec="seconds"))

        if self.count == 0 and len(self.events) > 0:
            object.__setattr__(self, "count", len(self.events))

    def to_natural_language(self):
        """Return a concise Korean response for TTS."""
        if self.message:
            return self.message

        if self.action in {"list", "get"}:
            return format_list_response(self)

        if self.action == "create":
            if self.success and self.events:
                return format_write_response("등록", self.events[0])
            return "일정을 등록하려면 확인이 필요합니다. 등록할까요?"

        if self.action == "update":
            if self.success and self.events:
                return format_write_response("수정", self.events[0])
            return "일정을 수정하려면 확인이 필요합니다. 수정할까요?"

        if self.action == "delete":
            if self.success and self.count > 0:
                return "일정을 삭제했습니다."
            return "삭제할 일정을 찾지 못했습니다."

        return str(self)


def format_list_response(result):
    """Return a natural language list response using the query date."""
    date_label = calendar_date_label(result)
    events = list(getattr(result, "events", []) or [])

    if len(events) == 0:
        return f"{date_label} 일정은 없습니다."

    if getattr(result, "date", "") == "next" or date_label == "다음":
        return f"다음 일정은 {format_event_summary(events[0])}입니다."

    lines = [f"{date_label} 일정은 {len(events)}건입니다."]

    for index, event in enumerate(events, start=1):
        lines.append(f"{index}. {format_event_summary(event)}")

    return "\n".join(lines)


def format_list_response_v2(result):
    """Compatibility alias for older callers."""
    return format_list_response(result)


def format_write_response(verb, event):
    """Return verified create/update response with saved details."""
    if verb == "등록":
        return f"일정을 등록했습니다. {format_event_detail(event)}"

    if verb == "수정":
        return f"일정을 수정했습니다. {format_event_detail(event)}"

    return f"{verb}이 완료되었습니다. {format_event_detail(event)}"


def format_event_detail(event):
    """Return a concrete saved-event description."""
    detail = format_event_summary(event)
    reminders = format_reminders(getattr(event, "reminder_minutes", []) or [])

    if reminders:
        return f"{detail}이며, {reminders}이 설정되어 있습니다."

    return f"{detail}입니다."


def format_event_summary(event):
    """Return compact event summary for speech."""
    title = str(getattr(event, "title", "") or "일정")
    date_text = format_korean_date(str(getattr(event, "date", "") or ""))
    time_text = format_korean_time(str(getattr(event, "time", "") or ""))
    location = str(getattr(event, "location", "") or "").strip()

    if time_text:
        summary = f"{date_text} {time_text} {title}".strip()
    else:
        summary = f"{date_text} 종일 {title}".strip()

    if location:
        summary = f"{summary}, 장소는 {location}"

    return summary


def calendar_date_label(result):
    """Return today/tomorrow/date label for a calendar result."""
    value = getattr(result, "date", "") or first_event_date(result)

    if value == "week":
        return "이번 주"

    if value == "next_week":
        return "다음 주"

    if value == "next":
        return "다음"

    current_date = today()
    tomorrow_date = (date.fromisoformat(current_date) + timedelta(days=1)).isoformat()

    if value in ["", "today", current_date]:
        return "오늘"

    if value in ["tomorrow", tomorrow_date]:
        return "내일"

    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value

    return f"{parsed.year}년 {parsed.month}월 {parsed.day}일"


def first_event_date(result):
    """Return the first event date if present."""
    if len(result.events) == 0:
        return ""

    return getattr(result.events[0], "date", "")


def format_korean_date(value):
    """Return a spoken Korean date label."""
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        return str(value or "").strip()

    current_date = today()
    tomorrow_date = (date.fromisoformat(current_date) + timedelta(days=1)).isoformat()

    if value == current_date:
        return "오늘"

    if value == tomorrow_date:
        return "내일"

    return f"{parsed.month}월 {parsed.day}일"


def format_korean_time(value):
    """Format HH:MM as Korean am/pm time."""
    if value == "":
        return ""

    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (TypeError, ValueError):
        return str(value or "")

    period = "오전" if hour < 12 else "오후"
    display_hour = hour if 1 <= hour <= 12 else abs(hour - 12)

    if display_hour == 0:
        display_hour = 12

    if minute == 0:
        return f"{period} {display_hour}시"

    return f"{period} {display_hour}시 {minute}분"


def format_reminders(minutes):
    """Return a natural reminder summary."""
    values = []

    for value in minutes:
        try:
            values.append(int(value))
        except (TypeError, ValueError):
            continue

    if not values:
        return ""

    labels = [format_reminder_minutes(value) for value in values]
    return ", ".join(labels) + " 알림"


def format_reminder_minutes(value):
    """Return natural Korean reminder offset."""
    if value == 1440:
        return "하루 전"

    if value % 60 == 0:
        return f"{value // 60}시간 전"

    return f"{value}분 전"
