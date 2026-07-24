import json
import re
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

from jarvis.abilities.metadata import AbilityMetadata, AbilityType
from jarvis.abilities.native.calendar.parser import CalendarIntentParser
from jarvis.abilities.native.calendar.provider import MockCalendarProvider
from jarvis.abilities.result import AbilityHealth, AbilityResult
from jarvis.core.events.event import BaseEvent
from jarvis.core.events.event_bus import InMemoryEventBus
from jarvis.core.events.handlers import ReminderScheduleHandler
from jarvis.debug_trace import trace_event
from jarvis.permissions import PermissionLevel


CONFIRM_REQUIRED_ACTIONS = ["create", "delete", "update"]


class CalendarAbility:
    """Native Calendar Ability with replaceable providers."""

    def __init__(self, provider=None, metadata=None, parser=None, reminder_engine=None, now_provider=None, event_bus=None):
        """Create Calendar Ability."""
        self.provider = provider or MockCalendarProvider()
        self.metadata = metadata or load_calendar_metadata()
        self.parser = parser or CalendarIntentParser()
        self.reminder_engine = reminder_engine
        self.event_bus = event_bus or create_calendar_event_bus(reminder_engine)
        self.now_provider = now_provider or datetime.now

    @property
    def id(self):
        """Return ability ID."""
        return self.metadata.id

    @property
    def name(self):
        """Return ability display name."""
        return self.metadata.name

    @property
    def type(self):
        """Return ability type."""
        return self.metadata.type

    @property
    def description(self):
        """Return ability description."""
        return self.metadata.description

    @property
    def permission(self):
        """Return base permission."""
        return self.metadata.permission

    def execute(self, input_data):
        """Execute Calendar action and return AbilityResult."""
        try:
            query = normalize_query(input_data, self.parser)
            trace_event(
                "calendar.query",
                action=query.action,
                date=query.date,
                time=query.time,
                title=query.title,
                participants=list(getattr(query, "participants", []) or []),
                location=getattr(query, "location", ""),
                time_scope=getattr(query, "time_scope", ""),
                position=getattr(query, "position", ""),
            )

            past_decision = past_calendar_create_decision(query, self.now_provider())

            if past_decision["past"] and not is_confirmed(input_data):
                if past_decision["query"] is not None:
                    future_query = past_decision["query"]
                    trace_event("calendar.permission", action=query.action, permission="confirm_required")
                    return AbilityResult(
                        success=True,
                        data=create_past_time_confirmation_result(
                            query,
                            future_query,
                            getattr(self.provider, "provider_name", ""),
                        ),
                        metadata={"ability_id": self.id, "query": future_query, "permission": "confirm_required"},
                    )

                return AbilityResult(
                    success=True,
                    data=create_past_time_block_result(query, getattr(self.provider, "provider_name", "")),
                    metadata={"ability_id": self.id, "query": query},
                )

            if past_decision["past"] and is_confirmed(input_data):
                return AbilityResult(
                    success=True,
                    data=create_past_time_block_result(query, getattr(self.provider, "provider_name", "")),
                    metadata={"ability_id": self.id, "query": query},
                )

            if query.action in CONFIRM_REQUIRED_ACTIONS and not is_confirmed(input_data):
                trace_event("calendar.permission", action=query.action, permission="confirm_required")
                return AbilityResult(
                    success=True,
                    data=create_confirmation_result(query, getattr(self.provider, "provider_name", "")),
                    metadata={"ability_id": self.id, "query": query, "permission": "confirm_required"},
                )

            result = self.execute_query(query)
            self.publish_calendar_event(query, result, input_data)

            trace_event(
                "calendar.result",
                action=result.action,
                provider=result.provider,
                events=len(result.events),
                success=result.success,
            )
            return AbilityResult(
                success=result.success,
                data=result,
                error=result.to_natural_language() if not result.success else "",
                metadata={"ability_id": self.id, "provider": result.provider, "query": query},
            )
        except Exception as error:
            return AbilityResult(success=False, error=str(error), metadata={"ability_id": self.id})

    def execute_query(self, query):
        """Dispatch one CalendarQuery."""
        if query.action == "list":
            trace_event("calendar.provider", action=query.action, provider=getattr(self.provider, "provider_name", ""))
            return self.provider.list_events(query)

        if query.action == "create":
            return self.provider.create_event(query)

        if query.action == "delete":
            return self.provider.delete_event(query)

        if query.action == "update":
            return self.provider.update_event(query)

        raise ValueError(f"Unsupported calendar action: {query.action}")

    def publish_calendar_event(self, query, result, input_data):
        """Publish Calendar mutation events for downstream handlers."""
        if self.event_bus is None or not getattr(result, "success", False):
            return None

        if query.action not in {"create", "delete", "update"}:
            return None

        event_type = {
            "create": "CalendarCreated",
            "delete": "CalendarDeleted",
            "update": "CalendarUpdated",
        }[query.action]
        remind_before = None

        if query.action in {"create", "update"} and not should_suppress_auto_reminder(input_data):
            remind_before = query.remind_before_minutes

            if remind_before is None:
                remind_before = parse_remind_before_minutes(getattr(query, "raw_text", ""))

        event = BaseEvent(
            event_type=event_type,
            aggregate_type="calendar",
            aggregate_id=first_calendar_event_id(result),
            revision=0,
            trace_id=extract_trace_id(input_data),
            correlation_id=extract_correlation_id(input_data),
            source=getattr(self.provider, "provider_name", "calendar"),
            payload={
                "action": query.action,
                "events": [event.to_dict() for event in result.events],
                "remind_before": remind_before,
                "suppress_auto_reminder": should_suppress_auto_reminder(input_data),
            },
            metadata={"provider": result.provider},
        )
        return self.event_bus.publish(event)

    def health(self):
        """Return provider health."""
        if hasattr(self.provider, "health"):
            return self.provider.health()

        return AbilityHealth(status="ok", provider=getattr(self.provider, "provider_name", ""))


def load_calendar_metadata():
    """Load Calendar manifest."""
    manifest_path = Path(__file__).with_name("manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    return AbilityMetadata(
        id=manifest["id"],
        name=manifest["name"],
        type=AbilityType(manifest["type"]),
        permission=PermissionLevel(manifest["permission"]),
        version=manifest["version"],
        author=manifest.get("author", "Jarvis"),
        description=manifest["description"],
        capabilities=list(manifest.get("capabilities", [])),
        input_schema=dict(manifest.get("input_schema", {})),
        output_schema=manifest.get("output_schema", "CalendarResult"),
        aliases=["calendar", "schedule", "appointment", "event", "meeting", "일정", "캘린더", "스케줄", "약속", "예약"],
        supported_intents=[
            "calendar",
            "schedule",
            "오늘 일정",
            "내일 일정",
            "이번주 일정",
            "일정 추가",
            "예약",
            "일정 삭제",
        ],
        examples=["오늘 일정 알려줘", "내일 오후 3시에 치과 예약해", "이번주 일정 알려줘"],
        input_prefixes=["calendar", "schedule", "캘린더", "스케줄"],
        route_confidence=0.75,
    )


def normalize_query(input_data, parser=None):
    """Return CalendarQuery from direct or routed input."""
    if hasattr(input_data, "action") and hasattr(input_data, "date"):
        return input_data

    if isinstance(input_data, dict) and "action" in input_data:
        from jarvis.abilities.native.calendar.query import CalendarQuery

        query = CalendarQuery(
            date=str(input_data.get("date", "")),
            time=str(input_data.get("time", "")),
            action=str(input_data.get("action", "list")),
            title=str(input_data.get("title", "")),
            description=str(input_data.get("description", "")),
            location=str(input_data.get("location", "")),
            participants=list(input_data.get("participants", [])),
            raw_text=str(input_data.get("raw_text", "")),
            event_id=str(input_data.get("event_id", "")),
            time_min=input_data.get("time_min"),
            time_max=input_data.get("time_max"),
            timezone=str(input_data.get("timezone", "Asia/Seoul")),
            limit=input_data.get("limit"),
            order_by=str(input_data.get("order_by", "start_time")),
            remind_before_minutes=read_remind_before_minutes(input_data),
            time_scope=str(input_data.get("time_scope", "")),
            position=str(input_data.get("position", "")),
        )
        return enrich_calendar_query_for_polish(query, query.raw_text)

    parser = parser or CalendarIntentParser()
    raw_text = ""

    if isinstance(input_data, dict):
        raw_text = input_data.get("raw_text") or input_data.get("text") or input_data.get("key") or ""
    else:
        raw_text = str(input_data or "")

    return enrich_calendar_query_for_polish(parser.parse(raw_text), raw_text)


def enrich_calendar_query_for_polish(query, raw_text):
    """Attach non-destructive calendar UX hints from the original utterance."""
    time_scope = parse_calendar_time_scope(raw_text)
    position = parse_calendar_position(raw_text)

    if time_scope == "" and position == "":
        return query

    return replace(query, time_scope=time_scope or getattr(query, "time_scope", ""), position=position or getattr(query, "position", ""))


def parse_calendar_time_scope(raw_text):
    """Return morning/afternoon/evening query scope from Korean text."""
    text = str(raw_text or "")

    if any(token in text for token in ["오전 일정", "아침 일정", "아침에", "오전만"]):
        return "morning"

    if any(token in text for token in ["오후 일정", "오후만", "낮 일정"]):
        return "afternoon"

    if any(token in text for token in ["저녁 일정", "밤 일정", "저녁에", "밤에"]):
        return "evening"

    return ""


def parse_calendar_position(raw_text):
    """Return first/last/next positional hint from Korean text."""
    text = str(raw_text or "")

    if any(token in text for token in ["첫 일정", "첫번째 일정", "첫 번째 일정"]):
        return "first"

    if any(token in text for token in ["마지막 일정", "끝 일정"]):
        return "last"

    if "다음 주" not in text and any(token in text for token in ["다음 일정", "다가오는 일정"]):
        return "next"

    return ""


def is_confirmed(input_data):
    """Return whether a mutating calendar action was confirmed."""
    if not isinstance(input_data, dict):
        return False

    return bool(input_data.get("_confirmed", input_data.get("confirmed", False)))


def should_suppress_auto_reminder(input_data):
    """Return whether planner-owned Reminder steps should handle reminders."""
    return isinstance(input_data, dict) and bool(input_data.get("_suppress_auto_reminder", False))


def parse_remind_before_minutes(text):
    """Return remind-before minutes from text, defaulting to 30."""
    normalized = str(text or "")

    day_match = re.search(r"(\d+)\s*일\s*전", normalized)

    if day_match:
        return int(day_match.group(1)) * 24 * 60

    if any(token in normalized for token in ["하루 전", "하루전에", "하루 전에"]):
        return 24 * 60

    hour_match = re.search(r"(\d+)\s*시간\s*전", normalized)

    if hour_match:
        return int(hour_match.group(1)) * 60

    minute_match = re.search(r"(\d+)\s*분\s*전", normalized)

    if minute_match:
        return int(minute_match.group(1))

    return 30


def read_remind_before_minutes(input_data):
    """Return reminder override minutes from structured or raw calendar input."""
    if not isinstance(input_data, dict):
        return None

    for key in ["remind_before_minutes", "remind_before", "reminder_minutes"]:
        value = input_data.get(key)

        if value in [None, ""]:
            continue

        try:
            return int(value)
        except (TypeError, ValueError):
            continue

    raw_text = str(input_data.get("raw_text") or input_data.get("text") or "")

    if raw_text:
        return parse_remind_before_minutes(raw_text)

    return None


def parse_remind_before_minutes(text):
    """Return remind-before minutes from text, defaulting to 30."""
    normalized = str(text or "")

    day_match = re.search(r"(\d+)\s*일\s*전", normalized)

    if day_match:
        return int(day_match.group(1)) * 1440

    if any(token in normalized for token in ["하루 전", "하루전에", "하루 전에"]):
        return 1440

    hour_match = re.search(r"(\d+)\s*시간\s*전", normalized)

    if hour_match:
        return int(hour_match.group(1)) * 60

    minute_match = re.search(r"(\d+)\s*분\s*전", normalized)

    if minute_match:
        return int(minute_match.group(1))

    return 30


def read_remind_before_minutes(input_data):
    """Return reminder override minutes from structured or raw calendar input."""
    if not isinstance(input_data, dict):
        return None

    for key in ["remind_before_minutes", "remind_before", "reminder_minutes"]:
        value = input_data.get(key)

        if value in [None, ""]:
            continue

        if isinstance(value, (list, tuple)) and value:
            value = value[0]

        try:
            return int(value)
        except (TypeError, ValueError):
            continue

    raw_text = str(input_data.get("raw_text") or input_data.get("text") or "")

    if raw_text:
        return parse_remind_before_minutes(raw_text)

    return None


CALENDAR_KOREAN_NUMBER_WORDS = {
    "\ud55c": 1,
    "\ud558\ub098": 1,
    "\ub450": 2,
    "\ub458": 2,
    "\uc138": 3,
    "\uc14b": 3,
    "\ub124": 4,
    "\ub137": 4,
    "\ub2e4\uc12f": 5,
    "\uc5ec\uc12f": 6,
    "\uc77c\uacf1": 7,
    "\uc5ec\ub35f": 8,
    "\uc544\ud649": 9,
    "\uc5f4": 10,
}


def parse_calendar_korean_number_word(value):
    """Return integer for a small Korean native number word."""
    return CALENDAR_KOREAN_NUMBER_WORDS.get(str(value or "").strip())


def parse_remind_before_minutes(text):
    """Return remind-before minutes from text, defaulting to 30."""
    normalized = str(text or "")

    day_match = re.search(r"(\d+)\s*\uc77c\s*\uc804", normalized)
    if day_match:
        return int(day_match.group(1)) * 1440

    if any(token in normalized for token in ["\ud558\ub8e8 \uc804", "\ud558\ub8e8\uc804\uc5d0", "\ud558\ub8e8 \uc804\uc5d0"]):
        return 1440

    hour_match = re.search(r"(\d+)\s*\uc2dc\uac04\s*\uc804", normalized)
    if hour_match:
        return int(hour_match.group(1)) * 60

    minute_match = re.search(r"(\d+)\s*\ubd84\s*\uc804", normalized)
    if minute_match:
        return int(minute_match.group(1))

    word_pattern = "|".join(re.escape(word) for word in sorted(CALENDAR_KOREAN_NUMBER_WORDS, key=len, reverse=True))

    word_hour_match = re.search(rf"({word_pattern})\s*\uc2dc\uac04\s*\uc804", normalized)
    if word_hour_match:
        return parse_calendar_korean_number_word(word_hour_match.group(1)) * 60

    word_minute_match = re.search(rf"({word_pattern})\s*\ubd84\s*\uc804", normalized)
    if word_minute_match:
        return parse_calendar_korean_number_word(word_minute_match.group(1))

    return 30


def past_calendar_create_decision(query, now):
    """Return whether a create query targets the past and any safe follow-up query."""
    query_datetime = calendar_query_datetime(query)

    if query_datetime is None or query_datetime > now:
        return {"past": False, "query": None}

    if query_datetime.date() == now.date():
        tomorrow = now.date() + timedelta(days=1)
        return {"past": True, "query": replace(query, date=tomorrow.isoformat())}

    return {"past": True, "query": None}


def calendar_query_datetime(query):
    """Return the scheduled datetime for a Calendar create query."""
    if getattr(query, "action", "") != "create":
        return None

    query_date = str(getattr(query, "date", "") or "").strip()
    query_time = str(getattr(query, "time", "") or "").strip()

    if query_date == "" or query_time == "":
        return None

    if len(query_time.split(":")) == 2:
        query_time = f"{query_time}:00"

    try:
        return datetime.fromisoformat(f"{query_date}T{query_time}")
    except ValueError:
        return None


def create_past_time_confirmation_result(original_query, future_query, provider):
    """Ask whether to move a same-day past event to tomorrow."""
    from jarvis.abilities.native.calendar.result import CalendarResult

    reference_date = calendar_query_date(original_query) or date.today()
    return CalendarResult(
        success=True,
        action=original_query.action,
        provider=provider,
        message=(
            f"{format_calendar_datetime_for_message(original_query, reference_date=reference_date)}는 이미 지났습니다. "
            f"{format_calendar_datetime_for_message(future_query, reference_date=reference_date)}로 등록할까요?"
        ),
    )


def create_past_time_block_result(query, provider):
    """Return a safe message for calendar create requests in the past."""
    from jarvis.abilities.native.calendar.result import CalendarResult

    return CalendarResult(
        success=False,
        action=query.action,
        provider=provider,
        message=f"{format_calendar_datetime_for_message(query)}는 이미 지났습니다. 다른 시간을 말씀해 주세요.",
    )


def format_calendar_datetime_for_message(query, reference_date=None):
    """Return a compact Korean date/time label for one query."""
    query_date = str(getattr(query, "date", "") or "")
    query_time = str(getattr(query, "time", "") or "")
    today_date = reference_date or date.today()

    try:
        parsed_date = date.fromisoformat(query_date)
    except ValueError:
        parsed_date = None

    if parsed_date == today_date:
        date_label = "오늘"
    elif parsed_date == today_date + timedelta(days=1):
        date_label = "내일"
    elif parsed_date is not None:
        date_label = f"{parsed_date.year}년 {parsed_date.month}월 {parsed_date.day}일"
    else:
        date_label = query_date or "해당 시간"

    return f"{date_label} {format_time_for_message(query_time)}".strip()


def calendar_query_date(query):
    """Return the date part of a Calendar query when valid."""
    try:
        return date.fromisoformat(str(getattr(query, "date", "") or ""))
    except ValueError:
        return None


def format_time_for_message(value):
    """Return Korean am/pm time label."""
    text = str(value or "").strip()

    if text == "":
        return ""

    try:
        parts = text.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        return text

    period = "오전" if hour < 12 else "오후"
    display_hour = hour if 1 <= hour <= 12 else abs(hour - 12)

    if display_hour == 0:
        display_hour = 12

    if minute == 0:
        return f"{period} {display_hour}시"

    return f"{period} {display_hour}시 {minute}분"


def create_confirmation_result(query, provider):
    """Return confirmation-required result."""
    from jarvis.abilities.native.calendar.result import CalendarResult

    messages = {
        "create": "일정을 등록하려면 확인이 필요합니다. 등록할까요?",
        "delete": "일정을 삭제하려면 확인이 필요합니다. 삭제할까요?",
        "update": "일정을 수정하려면 확인이 필요합니다. 수정할까요?",
    }
    return CalendarResult(
        success=True,
        action=query.action,
        provider=provider,
        message=messages.get(query.action, "이 작업은 확인이 필요합니다."),
    )


def create_ability(provider=None):
    """Create Calendar Ability."""
    return CalendarAbility(provider=provider)


def create_calendar_event_bus(reminder_engine):
    """Create a local event bus for calendar side effects when needed."""
    if reminder_engine is None:
        return None

    bus = InMemoryEventBus()
    handler = ReminderScheduleHandler(reminder_engine, event_bus=bus)
    bus.subscribe("CalendarCreated", handler)
    bus.subscribe("CalendarUpdated", handler)
    bus.subscribe("CalendarDeleted", handler)
    return bus


def first_calendar_event_id(result):
    """Return the first event ID in a calendar result."""
    events = list(getattr(result, "events", []) or [])

    if len(events) == 0:
        return ""

    return str(getattr(events[0], "id", "") or "")


def extract_trace_id(input_data):
    """Return trace ID from input data."""
    if isinstance(input_data, dict):
        return str(input_data.get("trace_id") or "")

    return ""


def extract_correlation_id(input_data):
    """Return correlation ID from input data."""
    if isinstance(input_data, dict):
        return str(input_data.get("correlation_id") or input_data.get("trace_id") or "")

    return ""
