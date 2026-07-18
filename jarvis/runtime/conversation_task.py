import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from time import perf_counter
from uuid import uuid4

from jarvis.debug_trace import trace_event


CALENDAR_TASK_ACTIVE = "active"
CALENDAR_TASK_COMPLETED = "completed"
CALENDAR_TASK_CANCELLED = "cancelled"
CALENDAR_TASK_EXPIRED = "expired"

CALENDAR_STATE_COLLECTING = "COLLECTING_INFORMATION"
CALENDAR_STATE_WAITING_CLARIFICATION = "WAITING_CLARIFICATION"
CALENDAR_STATE_WAIT_CONFIRMATION = "WAIT_CONFIRMATION"
CALENDAR_STATE_EXECUTING = "EXECUTING"
CALENDAR_STATE_COMPLETED = "COMPLETED"
CALENDAR_STATE_CANCELLED = "CANCELLED"
CALENDAR_STATE_EXPIRED = "EXPIRED"

DEFAULT_EXPIRES_TURNS = 8
DEFAULT_EXPIRES_SECONDS = 180.0
EXECUTE_CALENDAR_TASK = "__EXECUTE__"

FIELD_DATE = "date"
FIELD_TIME = "time"
FIELD_TITLE = "title"
FIELD_PARTICIPANTS = "participants"
FIELD_LOCATION = "location"
FIELD_REMIND_BEFORE_MINUTES = "remind_before_minutes"
COLLECTED_FIELDS = [FIELD_DATE, FIELD_TIME, FIELD_TITLE, FIELD_PARTICIPANTS, FIELD_LOCATION]
START_REQUIRED_FIELDS = [FIELD_DATE, FIELD_TIME, FIELD_TITLE]


@dataclass
class CalendarConversationTask:
    """Calendar-only multi-turn task for collecting event details."""

    id: str
    raw_text: str
    fields: dict = field(default_factory=dict)
    task_state: str = CALENDAR_TASK_ACTIVE
    state: str = CALENDAR_STATE_COLLECTING
    missing_fields: list[str] = field(default_factory=list)
    pending_clarification: str = ""
    conversation_turn: int = 0
    expires_turns: int = DEFAULT_EXPIRES_TURNS
    expires_at: float = field(default_factory=lambda: perf_counter() + DEFAULT_EXPIRES_SECONDS)
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    selected_entity: str = ""
    final_confirmation_text: str = ""
    pending_date_candidate: str = ""
    pending_date_question: str = ""
    optional_fields_done: list[str] = field(default_factory=list)

    def refresh(self):
        """Refresh activity metadata."""
        self.last_updated = current_timestamp()

    def advance_turn(self):
        """Age one conversation turn."""
        self.conversation_turn += 1
        self.expires_turns -= 1
        self.refresh()

    def is_expired(self):
        """Return whether this task expired."""
        return self.expires_turns <= 0 or perf_counter() > self.expires_at


def start_calendar_conversation_task(text):
    """Create a Calendar conversation task and return its first question."""
    task = CalendarConversationTask(id=create_calendar_task_id(), raw_text=str(text or ""))
    merge_calendar_fields(task, extract_calendar_fields(text))
    update_missing_fields(task)
    trace_conversation(task, missing=",".join(task.missing_fields))
    return task


def update_calendar_conversation_task(task, text):
    """Apply one follow-up utterance to an active Calendar task."""
    if task.is_expired():
        task.task_state = CALENDAR_TASK_EXPIRED
        task.state = CALENDAR_STATE_EXPIRED
        trace_conversation(task)
        return "일정 등록 작업이 만료되었습니다. 다시 말씀해 주세요."

    task.advance_turn()

    possible_updates = extract_calendar_fields(text, pending_field=getattr(task, "pending_clarification", ""))

    if is_cancel_text(text) and not possible_updates and not contains_any(text, ["바꿔", "수정", "말고"]):
        task.task_state = CALENDAR_TASK_CANCELLED
        task.state = CALENDAR_STATE_CANCELLED
        trace_conversation(task)
        return "일정 등록을 취소했습니다."

    if task.state == CALENDAR_STATE_WAIT_CONFIRMATION:
        if contains_any(text, ["바꿔", "수정"]):
            correction_updates = extract_calendar_fields(text)
            title_candidate = participant_answer_to_title(text)

            if title_candidate:
                correction_updates[FIELD_TITLE] = title_candidate
                task.fields[FIELD_PARTICIPANTS] = []
                mark_optional_field_done(task, FIELD_PARTICIPANTS)
                trace_event("conversation.field_updated", task_id=task.id, field=FIELD_PARTICIPANTS, value=[])

            if correction_updates:
                merge_calendar_fields(task, correction_updates)
                update_missing_fields(task)
                trace_conversation(task, missing=",".join(task.missing_fields))

                if task.pending_clarification:
                    return question_for_field(task.pending_clarification)

                task.state = CALENDAR_STATE_WAIT_CONFIRMATION
                trace_conversation(task)
                return confirmation_question(task)

        decision = confirmation_decision(text)

        if decision == "yes":
            task.final_confirmation_text = str(text or "")
            task.raw_text = f"{task.raw_text} {text}".strip()
            reminder_minutes = calendar_conversation_reminder_minutes(task)

            if reminder_minutes is not None:
                merge_calendar_fields(task, {FIELD_REMIND_BEFORE_MINUTES: reminder_minutes})

            task.state = CALENDAR_STATE_EXECUTING
            trace_conversation(task)
            return EXECUTE_CALENDAR_TASK

        if decision == "no":
            task.task_state = CALENDAR_TASK_CANCELLED
            task.state = CALENDAR_STATE_CANCELLED
            trace_conversation(task)
            return "일정 등록을 취소했습니다."

        if is_confirmation_noise_text(text):
            trace_event("conversation.confirmation_unknown", task_id=task.id, text=normalize_confirmation_text(text))
            return confirmation_question(task)

        correction_updates = extract_calendar_fields(text)

        if correction_updates:
            title_candidate = participant_answer_to_title(text)

            if title_candidate:
                correction_updates[FIELD_TITLE] = title_candidate
                task.fields[FIELD_PARTICIPANTS] = []
                mark_optional_field_done(task, FIELD_PARTICIPANTS)
                trace_event("conversation.field_updated", task_id=task.id, field=FIELD_PARTICIPANTS, value=[])

            merge_calendar_fields(task, correction_updates)
            update_missing_fields(task)
            trace_conversation(task, missing=",".join(task.missing_fields))

            if task.pending_clarification:
                return question_for_field(task.pending_clarification)

            task.state = CALENDAR_STATE_WAIT_CONFIRMATION
            trace_conversation(task)
            return confirmation_question(task)

        return "등록할까요? 네 또는 아니오로 답해주세요."

    pending_field = task.pending_clarification

    if pending_field == FIELD_DATE and task.pending_date_candidate and possible_updates:
        task.pending_date_candidate = ""
        task.pending_date_question = ""
        trace_event("conversation.correction_detected", task_id=task.id, value=True)
        merge_calendar_fields(task, possible_updates)
        update_missing_fields(task)
        trace_conversation(task, missing=",".join(task.missing_fields))

        if task.pending_clarification:
            return question_for_field(task.pending_clarification)

        task.state = CALENDAR_STATE_WAIT_CONFIRMATION
        trace_conversation(task)
        return confirmation_question(task)

    if pending_field == FIELD_DATE and task.pending_date_candidate and confirmation_decision(text) == "yes":
        merge_calendar_fields(task, {FIELD_DATE: task.pending_date_candidate})
        task.pending_date_candidate = ""
        task.pending_date_question = ""
        update_missing_fields(task)
        trace_conversation(task, missing=",".join(task.missing_fields))

        if task.pending_clarification:
            return question_for_field(task.pending_clarification)

        task.state = CALENDAR_STATE_WAIT_CONFIRMATION
        trace_conversation(task)
        return confirmation_question(task)

    if pending_field == FIELD_DATE and task.pending_date_candidate and confirmation_decision(text) == "no":
        task.pending_date_candidate = ""
        task.pending_date_question = ""
        trace_event("conversation.correction_detected", task_id=task.id, value=True)
        trace_conversation(task, missing=",".join(task.missing_fields))
        return question_for_field(FIELD_DATE)

    updates = possible_updates
    optional_skipped = pending_field in [FIELD_PARTICIPANTS, FIELD_LOCATION] and is_optional_skip_text(text)
    past_day = past_day_only_candidate(text)

    if pending_field == FIELD_DATE and not updates.get(FIELD_DATE) and past_day:
        task.pending_date_candidate = past_day["candidate_date"]
        task.pending_date_question = past_day["question"]
        merge_calendar_fields(task, {key: value for key, value in updates.items() if key != FIELD_DATE})
        update_missing_fields(task)
        trace_conversation(task, missing=",".join(task.missing_fields))
        return past_day["question"]

    if optional_skipped:
        mark_optional_field_done(task, pending_field)
        updates.pop(pending_field, None)

    elif (
        pending_field == FIELD_PARTICIPANTS
        and not updates.get(FIELD_PARTICIPANTS)
        and not updates.get(FIELD_DATE)
        and not updates.get(FIELD_TIME)
    ):
        title_candidate = participant_answer_to_title(text)

        if title_candidate:
            updates[FIELD_TITLE] = title_candidate
            mark_optional_field_done(task, FIELD_PARTICIPANTS)
        else:
            participants = split_people(text)

            if participants:
                updates[FIELD_PARTICIPANTS] = participants

    if pending_field == FIELD_LOCATION and not optional_skipped and not updates.get(FIELD_LOCATION):
        updates[FIELD_LOCATION] = strip_location_prefix(text)
        mark_optional_field_done(task, FIELD_LOCATION)

    merge_calendar_fields(task, updates)
    update_missing_fields(task)
    trace_conversation(task, missing=",".join(task.missing_fields))

    if task.pending_clarification:
        return question_for_field(task.pending_clarification)

    task.state = CALENDAR_STATE_WAIT_CONFIRMATION
    trace_conversation(task)
    return confirmation_question(task)


def should_start_calendar_conversation(text):
    """Return whether text should start Calendar missing-info collection."""
    normalized = normalize_text(text)

    if not is_calendar_create_text(normalized):
        return False

    # Multi-tool reminder phrases belong to the Planner path.
    if contains_any(normalized, ["알려", "알림", "리마인더", "전"]):
        return False

    fields = extract_calendar_fields(normalized)
    missing = [field for field in START_REQUIRED_FIELDS if not field_value_present(fields.get(field))]

    if len(missing) > 0:
        return True

    return needs_participant_clarification(normalized, fields)


def needs_participant_clarification(text, fields):
    """Return whether a meeting-like create command is missing the person."""
    if field_value_present(fields.get(FIELD_PARTICIPANTS)):
        return False

    title = str(fields.get(FIELD_TITLE, "") or "")
    combined = f"{text} {title}"
    return contains_any(combined, ["만나", "만남"])


def is_calendar_conversation_active(session):
    """Return whether a session has an active Calendar conversation task."""
    if session is None or not hasattr(session, "get_conversation_task"):
        return False

    task = session.get_conversation_task()
    return task is not None and getattr(task, "task_state", "") == CALENDAR_TASK_ACTIVE


def build_calendar_input(task, confirmed=True):
    """Build CalendarAbility input data from collected fields."""
    fields = dict(task.fields)
    return {
        "action": "create",
        "date": fields.get(FIELD_DATE, ""),
        "time": fields.get(FIELD_TIME, ""),
        "title": normalize_calendar_input_title(fields),
        "participants": list(fields.get(FIELD_PARTICIPANTS, []) or []),
        "location": fields.get(FIELD_LOCATION, ""),
        "raw_text": task.raw_text,
        "_confirmed": bool(confirmed),
    }


def normalize_calendar_input_title(fields):
    """Return a storage title that keeps generic meeting titles useful."""
    title = str(fields.get(FIELD_TITLE, "") or "").strip()
    people = format_people_label(fields.get(FIELD_PARTICIPANTS, []) or [])

    if people and title in {"만나기", "만남"}:
        return f"{people} 만나기"

    return title


def calendar_conversation_reminder_minutes(task):
    """Return requested reminder minutes from the final confirmation text."""
    fields = getattr(task, "fields", {}) or {}

    if field_value_present(fields.get(FIELD_REMIND_BEFORE_MINUTES)):
        return int(fields.get(FIELD_REMIND_BEFORE_MINUTES))

    text = f"{getattr(task, 'raw_text', '')} {getattr(task, 'final_confirmation_text', '')}"

    if not contains_any(text, ["알려", "알림", "알람", "리마인더"]):
        return None

    hour_match = re.search(r"(\d+)\s*시간\s*전", text)

    if hour_match:
        return int(hour_match.group(1)) * 60

    minute_match = re.search(r"(\d+)\s*분\s*전", text)

    if minute_match:
        return int(minute_match.group(1))

    return None


def extract_calendar_fields(text, pending_field=""):
    """Extract lightweight Calendar create fields from Korean text."""
    normalized = normalize_calendar_stt_text(text)
    fields = {}

    date_value = extract_date(normalized)
    time_value = extract_time(normalized)
    title = extract_title(normalized)
    participants = extract_participants(normalized)
    location = extract_location(normalized)

    if date_value:
        fields[FIELD_DATE] = date_value
    if time_value:
        fields[FIELD_TIME] = time_value
    if title and pending_field in ["", FIELD_TITLE]:
        fields[FIELD_TITLE] = title
    if participants:
        fields[FIELD_PARTICIPANTS] = participants
    if location:
        fields[FIELD_LOCATION] = location

    return fields


def merge_calendar_fields(task, updates):
    """Merge non-empty field updates and trace changed fields."""
    for key, value in (updates or {}).items():
        if key == FIELD_TITLE:
            value = normalize_topic_title(value)
            if not is_valid_title(value):
                continue
        elif not field_value_present(value):
            continue

        previous = task.fields.get(key)
        task.fields[key] = value

        if previous != value:
            trace_event("conversation.field_updated", task_id=task.id, field=key, value=value)

    task.refresh()


def update_missing_fields(task):
    """Update missing fields and task state."""
    task.missing_fields = [
        field for field in START_REQUIRED_FIELDS if not field_value_present(task.fields.get(field))
    ]

    if len(task.missing_fields) == 0:
        optional_field = next_optional_calendar_field(task)

        if optional_field:
            task.missing_fields = [optional_field]

    task.pending_clarification = task.missing_fields[0] if task.missing_fields else ""
    task.state = CALENDAR_STATE_WAITING_CLARIFICATION if task.pending_clarification else CALENDAR_STATE_COLLECTING


def next_optional_calendar_field(task):
    """Return the next optional field worth asking for this Calendar task."""
    optional_done = set(getattr(task, "optional_fields_done", []) or [])

    if (
        FIELD_PARTICIPANTS not in optional_done
        and not field_value_present(task.fields.get(FIELD_PARTICIPANTS))
        and should_ask_participants(task)
    ):
        return FIELD_PARTICIPANTS

    if (
        FIELD_LOCATION not in optional_done
        and not field_value_present(task.fields.get(FIELD_LOCATION))
        and should_ask_location(task)
    ):
        return FIELD_LOCATION

    return ""


def should_ask_participants(task):
    """Return whether this event type probably needs participants."""
    text = f"{getattr(task, 'raw_text', '')} {task.fields.get(FIELD_TITLE, '')}"
    return contains_any(text, ["약속", "회의", "미팅", "만나", "만남"])


def should_ask_location(task):
    """Return whether to ask the optional location once."""
    return True


def mark_optional_field_done(task, field):
    """Mark an optional field as answered or intentionally skipped."""
    if field not in task.optional_fields_done:
        task.optional_fields_done.append(field)


def field_value_present(value):
    """Return whether a collected field has a usable value."""
    if isinstance(value, list):
        return len(value) > 0
    return str(value or "").strip() != ""


def question_for_field(field):
    """Return one Korean clarification question for a Calendar field."""
    questions = {
        FIELD_DATE: "언제 일정으로 등록할까요?",
        FIELD_TIME: "몇 시에 등록할까요?",
        FIELD_TITLE: "어떤 일정으로 등록할까요?",
        FIELD_PARTICIPANTS: "누구와 만나는 일정인가요?",
        FIELD_LOCATION: "장소는 어디인가요?",
    }
    return questions.get(field, "조금 더 자세히 말씀해 주세요.")


def confirmation_question(task):
    """Return the final confirmation question."""
    fields = task.fields
    date_label = format_date_label(fields.get(FIELD_DATE, ""))
    time_label = format_time_label(fields.get(FIELD_TIME, ""))
    people = format_people_label(fields.get(FIELD_PARTICIPANTS, []) or [])
    location = fields.get(FIELD_LOCATION, "")
    title = fields.get(FIELD_TITLE, "일정")
    location_text = f"{location}에서 " if location else ""
    event_text = format_event_confirmation_label(title, people)
    return f"{date_label} {time_label}, {location_text}{event_text} 일정으로 등록할까요?"


def format_event_confirmation_label(title, people):
    """Return a natural Korean event label for final confirmation."""
    title = str(title or "일정").strip()

    if not people:
        return title

    if title in {"만나기", "만남"}:
        return f"{people}와 만나는"

    return f"{people}와 {title}"


def is_calendar_create_text(text):
    """Return whether text looks like a Calendar create request."""
    return contains_any(text, ["약속", "일정", "예약"]) and contains_any(
        text, ["잡아", "등록", "넣어", "추가", "만들어"]
    )


def extract_date(text):
    """Extract today/tomorrow/day-after-tomorrow or ISO-like date."""
    today_date = date.today()

    if "모레" in text:
        return (today_date + timedelta(days=2)).isoformat()
    if "내일" in text:
        return (today_date + timedelta(days=1)).isoformat()
    if "오늘" in text:
        return today_date.isoformat()

    matches = list(re.finditer(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", text))
    if matches:
        match = matches[-1]
        month = int(match.group(1))
        day = int(match.group(2))
        year = today_date.year
        return date(year, month, day).isoformat()

    matches = list(re.finditer(r"(?:오는\s*)?(?:이번\s*달\s*)?(\d{1,2})\s*일", text))
    if matches:
        match = matches[-1]
        day = int(match.group(1))
        year = today_date.year
        month = today_date.month

        if day < today_date.day:
            return ""

        return date(year, month, day).isoformat()

    return ""


def extract_time(text):
    """Extract a HH:MM time, treating bare 1-6 as afternoon."""
    word_time = extract_korean_word_time(text)

    if word_time:
        return word_time

    match = re.search(r"(오전|오후)?\s*(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?", text)

    if not match:
        return ""

    period = match.group(1) or ""
    hour = int(match.group(2))
    minute = int(match.group(3) or 0)

    if period == "오후" and hour < 12:
        hour += 12
    elif period == "오전" and hour == 12:
        hour = 0
    elif period == "" and 1 <= hour <= 6:
        hour += 12

    return f"{hour:02d}:{minute:02d}"


def extract_korean_word_time(text):
    """Extract time from Korean spoken numerals such as '오후 세시'."""
    normalized = normalize_text(text)
    hour_words = {
        "한": 1,
        "하나": 1,
        "두": 2,
        "둘": 2,
        "세": 3,
        "셋": 3,
        "네": 4,
        "넷": 4,
        "다섯": 5,
        "여섯": 6,
        "일곱": 7,
        "여덟": 8,
        "아홉": 9,
        "열": 10,
        "열한": 11,
        "열하나": 11,
        "열두": 12,
        "열둘": 12,
    }
    minute_words = {
        "반": 30,
        "영": 0,
        "정각": 0,
    }
    pattern = r"(오전|오후)?\s*(열두|열하나|열한|열둘|열|아홉|여덟|일곱|여섯|다섯|하나|한|둘|두|셋|세|넷|네)\s*시(?:\s*(반|정각|영)\s*분?)?"
    match = re.search(pattern, normalized)

    if not match:
        return ""

    period = match.group(1) or ""
    hour = hour_words.get(match.group(2), 0)
    minute = minute_words.get(match.group(3) or "", 0)

    if hour <= 0:
        return ""

    if period == "오후" and hour < 12:
        hour += 12
    elif period == "오전" and hour == 12:
        hour = 0
    elif period == "" and 1 <= hour <= 6:
        hour += 12

    return f"{hour:02d}:{minute:02d}"


def extract_title(text):
    """Extract a compact calendar title."""
    if "약속" in text:
        return "약속"

    if "예약" in text:
        return "예약"

    cleaned = cleanup_title(text)
    return cleaned if is_valid_title(cleaned) else ""


def extract_participants(text):
    """Extract participants from simple Korean person phrases."""
    people = []
    for person in ["아야", "유이", "유리"]:
        if person in text:
            people.append(person)

    if people:
        return people

    if "와" in text or "랑" in text:
        prefix = re.split(r"(?:만나|약속|일정|예약)", text, maxsplit=1)[0]
        return split_people(prefix)

    return []


def extract_location(text):
    """Extract location from common location phrases."""
    match = re.search(r"(?:장소는|장소|위치는|위치|에서)\s*([가-힣A-Za-z0-9 ]+)", text)

    if not match:
        return ""

    value = strip_location_prefix(match.group(1))
    value = re.split(r"\s*(?:로|으로)?\s*(?:등록|일정)", value, maxsplit=1)[0]
    return value.strip()


def split_people(text):
    """Split a participant answer into person names."""
    cleaned = cleanup_title(text)
    cleaned = re.sub(r"(내일|오늘|모레|오전|오후)", " ", cleaned)
    cleaned = re.sub(r"\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?", " ", cleaned)
    parts = [part.strip(" ,") for part in re.split(r"\s*(?:와|이랑|랑|하고|,|및)\s*", cleaned)]
    return [part for part in parts if is_person_like_participant(part)]


def participant_answer_to_title(text):
    """Return a title if a participant answer is actually a topic/task."""
    cleaned = normalize_topic_title(text)

    if cleaned == "" or is_optional_skip_text(cleaned):
        return ""

    if contains_known_person(cleaned):
        return ""

    if contains_any(cleaned, ["급여", "보험", "병원", "진료", "정비", "운동", "업무", "서류", "상담"]):
        return cleaned

    return ""


def normalize_topic_title(text):
    """Normalize common non-person topic titles."""
    cleaned = cleanup_title(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    replacements = {
        "실업 급여": "실업급여",
        "고용 보험": "고용보험",
        "병원 진료": "병원진료",
        "차량 정비": "차량정비",
    }

    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)

    return cleaned


def contains_known_person(text):
    """Return whether text mentions a known person."""
    return any(person in str(text or "") for person in ["아야", "유이", "유리"])


def is_person_like_participant(text):
    """Return whether a split participant candidate looks like a person."""
    candidate = str(text or "").strip()

    if candidate == "":
        return False

    if contains_known_person(candidate):
        return True

    if contains_any(candidate, ["급여", "보험", "병원", "진료", "정비", "운동", "업무", "서류", "상담"]):
        return False

    return len(candidate.replace(" ", "")) <= 4


def is_optional_skip_text(text):
    """Return whether the user wants to skip an optional slot."""
    normalized = normalize_text(text)
    return contains_any(
        normalized,
        [
            "혼자",
            "없어",
            "없음",
            "아직 몰라",
            "몰라",
            "장소는 아직",
            "그냥 등록",
            "바로 등록",
            "넘어가",
            "생략",
        ],
    )


def strip_location_prefix(text):
    """Clean a location answer."""
    value = str(text or "").strip()
    value = re.sub(r"^(장소는|장소|위치는|위치)\s*", "", value)
    value = re.sub(r"\s*(이야|입니다|로|으로)?\s*(해줘|해 줘)?$", "", value).strip()
    return value


def cleanup_title(text):
    """Remove common command fragments from a title candidate."""
    cleaned = str(text or "")
    cleaned = re.split(r"(?:아니고|말고)", cleaned)[-1]
    for token in [
        "아니",
        "내일",
        "오늘",
        "모레",
        "오전",
        "오후",
        "약속 잡아줘",
        "약속 잡아 줘",
        "잡아줘",
        "잡아 줘",
        "일정 등록해",
        "일정 등록해 줘",
        "일정 잡아 줘",
        "일정 잡아줘",
        "일정 추가해",
        "일정 넣어 줘",
        "일정 만들어 줘",
        "로 바꿔줘",
        "로 바꿔 줘",
        "으로 바꿔줘",
        "으로 바꿔 줘",
        "등록해줘",
        "등록해 줘",
        "등록해",
        "추가해",
        "넣어 줘",
        "만들어 줘",
        "바꿔줘",
        "바꿔 줘",
        "일정",
    ]:
        cleaned = cleaned.replace(token, " ")
    cleaned = re.sub(r"\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?", " ", cleaned)
    cleaned = re.sub(r"[,.]", " ", cleaned)
    cleaned = re.sub(r"\s+(로|으로)$", " ", cleaned)
    cleaned = re.sub(r"^(에|에서)\s+", " ", cleaned.strip())
    return re.sub(r"\s+", " ", cleaned).strip()


def past_day_only_candidate(text):
    """Return clarification data for a day-only date that already passed this month."""
    normalized = normalize_text(text)

    if re.search(r"\d{1,2}\s*월\s*\d{1,2}\s*일", normalized):
        return {}

    matches = list(re.finditer(r"(?:오는\s*)?(?:이번\s*달\s*)?(\d{1,2})\s*일", normalized))

    if not matches:
        return {}

    today_date = date.today()
    day = int(matches[-1].group(1))

    if day >= today_date.day:
        return {}

    year = today_date.year
    month = today_date.month + 1

    if month > 12:
        month = 1
        year += 1

    candidate = date(year, month, day)
    return {
        "candidate_date": candidate.isoformat(),
        "question": f"이번 달 {day}일은 이미 지났습니다. 다음 달 {day}일을 말씀하신 건가요?",
    }


def is_valid_title(value):
    """Return whether a title is real content, not a command fragment."""
    title = str(value or "").strip()

    if title == "":
        return False

    invalid_titles = {
        "등록해",
        "등록해 줘",
        "추가해",
        "넣어 줘",
        "만들어 줘",
        "잡아줘",
        "잡아 줘",
        "일정",
        "새 일정",
    }
    return title not in invalid_titles


def format_date_label(value):
    """Return a Korean date label."""
    target = str(value or "")
    today_date = date.today()

    if target == today_date.isoformat():
        return "오늘"
    if target == (today_date + timedelta(days=1)).isoformat():
        return "내일"
    if target == (today_date + timedelta(days=2)).isoformat():
        return "모레"
    return target


def format_time_label(value):
    """Return a Korean time label."""
    if not value:
        return ""

    hour = int(str(value).split(":")[0])
    minute = int(str(value).split(":")[1]) if ":" in str(value) else 0
    period = "오전" if hour < 12 else "오후"
    display_hour = hour if 1 <= hour <= 12 else abs(hour - 12)

    if display_hour == 0:
        display_hour = 12

    if minute == 0:
        return f"{period} {display_hour}시"

    return f"{period} {display_hour}시 {minute}분"


def format_people_label(people):
    """Return a natural Korean people list."""
    names = [str(person).strip() for person in people if str(person).strip()]

    if len(names) == 0:
        return ""

    if len(names) == 1:
        return names[0]

    return "와 ".join(names)


def confirmation_decision(text):
    """Return yes/no/unknown."""
    normalized = normalize_confirmation_text(text)

    if confirmation_text_matches(
        normalized,
        [
            "응",
            "웅",
            "음",
            "어",
            "엉",
            "응응",
            "네",
            "넵",
            "넥",
            "예",
            "예스",
            "그래",
            "그럼",
            "좋아",
            "등록",
            "삭제해",
            "삭제해 줘",
            "응 삭제해",
            "응 삭제해 줘",
            "수정해",
            "수정해 줘",
            "응 수정해",
            "응 수정해 줘",
            "해줘",
            "해 줘",
            "맞아",
            "gronn",
            "gron",
            "grown",
            "green",
            "\u55ef",
            "\u55ef\u55ef",
        ],
    ):
        return "yes"

    if confirmation_text_matches(normalized, ["아니", "취소", "하지마", "안 해", "됐어"]):
        return "no"

    return ""


def confirmation_text_matches(text, aliases):
    """Return whether normalized confirmation text matches a safe alias."""
    compact_text = str(text or "").replace(" ", "")

    for alias in aliases:
        normalized_alias = normalize_confirmation_text(alias)
        compact_alias = normalized_alias.replace(" ", "")

        if text == normalized_alias or compact_text == compact_alias:
            return True

        if len(compact_alias) <= 1:
            continue

        if normalized_alias and normalized_alias in text:
            return True

        if compact_alias and compact_alias in compact_text:
            return True

    return False


def is_cancel_text(text):
    """Return whether the user cancelled the task."""
    normalized = normalize_text(text)

    explicit_cancel_phrases = [
        "취소",
        "취소해",
        "취소해 줘",
        "일정 등록 취소",
        "등록 취소",
        "그만해",
        "그만",
        "안 할래",
        "안할래",
        "됐어 취소",
        "됐어, 취소",
    ]
    return normalized in explicit_cancel_phrases or contains_any(normalized, explicit_cancel_phrases)


def contains_any(text, tokens):
    """Return whether text contains any token."""
    return any(token in str(text or "") for token in tokens)


def normalize_calendar_stt_text(text):
    """Normalize Calendar-specific STT artifacts without changing global speech."""
    normalized = normalize_text(text)
    replacements = {
        "Aja.": "아야",
        "Aja": "아야",
        "aja.": "아야",
        "aja": "아야",
        "나의 만나기": "아야 만나기",
        "나의 만나": "아야 만나",
    }

    for source, target in replacements.items():
        normalized = normalized.replace(source, target)

    return normalized


def normalize_text(text):
    """Normalize whitespace."""
    return " ".join(str(text or "").strip().split())


def normalize_confirmation_text(text):
    """Normalize short STT confirmation text, including Latin artifacts."""
    normalized = normalize_text(text).lower().strip(".?! ")
    decomposed = unicodedata.normalize("NFKD", normalized)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return unicodedata.normalize("NFC", stripped)


def is_confirmation_noise_text(text):
    """Return whether an unknown confirmation utterance is likely STT noise."""
    compact = normalize_confirmation_text(text).replace(" ", "")

    if compact == "":
        return True

    if compact in ["o", "oh", "uh", "um", "mm", "hm"]:
        return True

    if len(compact) <= 3 and not any("\uac00" <= char <= "\ud7a3" for char in compact):
        return True

    return False


def current_timestamp():
    """Return local ISO timestamp."""
    return datetime.now().isoformat(timespec="seconds")


def create_calendar_task_id():
    """Return readable runtime task ID."""
    return f"RT-{uuid4().hex[:8].upper()}"


def trace_conversation(task, missing=""):
    """Trace conversation task state."""
    trace_event(
        "conversation.task",
        task_id=task.id,
        state=task.state,
        task_state=task.task_state,
        missing=missing,
        turn=task.conversation_turn,
    )
