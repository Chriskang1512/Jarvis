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

        if self.action == "list":
            return format_list_response_v2(self)

        if self.action == "create":
            if self.success and len(self.events) > 0:
                return "일정을 등록했습니다."

            return "일정 생성은 확인이 필요합니다."

        if self.action == "delete":
            if self.success and self.count > 0:
                return "일정을 삭제했습니다."

            if self.success:
                return "삭제할 일정을 찾지 못했습니다."

            return "일정 삭제에 실패했습니다."

        if self.action == "update":
            if self.success:
                return "일정을 수정했습니다."

            return "일정 수정은 확인이 필요합니다."

        return str(self)


def format_list_response_v2(result):
    """Return a natural language list response using the query date."""
    date_label = calendar_date_label(result)

    if len(result.events) == 0:
        return f"{date_label}\uc740 \uc77c\uc815\uc774 \uc5c6\uc2b5\ub2c8\ub2e4."

    lines = [f"{date_label} \uc77c\uc815\uc740 {len(result.events)}\uac74\uc785\ub2c8\ub2e4."]

    for event in result.events:
        prefix = format_korean_time(event.time)

        if prefix:
            lines.append(f"{prefix} {event.title}")
        else:
            lines.append(event.title)

    return "\n".join(lines)


def calendar_date_label(result):
    """Return today/tomorrow/date label for a calendar result."""
    value = getattr(result, "date", "") or first_event_date(result)

    if value == "week":
        return "\uc774\ubc88 \uc8fc"

    if value == "next_week":
        return "\ub2e4\uc74c \uc8fc"

    if value == "next":
        return "\ub2e4\uc74c"

    current_date = today()
    tomorrow_date = (date.fromisoformat(current_date) + timedelta(days=1)).isoformat()

    if value in ["", "today", current_date]:
        return "\uc624\ub298"

    if value in ["tomorrow", tomorrow_date]:
        return "\ub0b4\uc77c"

    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value

    return f"{parsed.year}\ub144 {parsed.month}\uc6d4 {parsed.day}\uc77c"


def first_event_date(result):
    """Return the first event date if present."""
    if len(result.events) == 0:
        return ""

    return getattr(result.events[0], "date", "")


def format_list_response(result):
    """Return a natural language list response."""
    if len(result.events) == 0:
        return "오늘은 일정이 없습니다."

    lines = [f"오늘 일정은 {len(result.events)}건입니다."]

    for event in result.events:
        prefix = format_korean_time(event.time)

        if prefix:
            lines.append(f"{prefix} {event.title}")
        else:
            lines.append(event.title)

    return "\n".join(lines)


def format_korean_time(value):
    """Format HH:MM as Korean am/pm time."""
    if value == "":
        return ""

    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        return value

    period = "오전" if hour < 12 else "오후"
    display_hour = hour if 1 <= hour <= 12 else abs(hour - 12)

    if display_hour == 0:
        display_hour = 12

    if minute == 0:
        return f"{period} {display_hour}시"

    return f"{period} {display_hour}시 {minute}분"
