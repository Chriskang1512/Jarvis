import re
from datetime import date, timedelta

from jarvis.abilities.native.calendar.query import CalendarQuery
from jarvis.date_calculator import today
from jarvis.voice.user_vocabulary import normalize_stt_text


def parse_calendar_intent(text):
    """Parse text into a CalendarQuery."""
    raw_text = str(text or "").strip()
    normalized_text = normalize_calendar_text(raw_text)
    action = detect_action(normalized_text)
    date_value = detect_date(normalized_text)
    time_value = detect_time(normalized_text)
    title = extract_title(normalized_text, action)
    participants = extract_participants(normalized_text)

    return CalendarQuery(
        date=date_value,
        time=time_value,
        action=action,
        title=title,
        participants=participants,
        raw_text=raw_text,
    )


class CalendarIntentParser:
    """Parse Korean calendar intents."""

    def parse(self, text):
        """Return a normalized CalendarQuery."""
        return parse_calendar_intent(text)


def detect_action(text):
    """Detect calendar action."""
    if contains_any(text, ["삭제", "지워", "취소"]):
        return "delete"

    if contains_any(text, ["수정", "변경"]):
        return "update"

    if contains_any(text, ["예약", "일정 추가", "추가", "등록", "잡아"]):
        return "create"

    return "list"


def detect_date(text):
    """Detect date scope or ISO date."""
    if "\ub2e4\uc74c \uc8fc" in text or "\ub2e4\uc74c\uc8fc" in text:
        return "next_week"

    if "\ub2e4\uc74c \uc77c\uc815" in text or "\ub2e4\uc74c\uc77c\uc815" in text:
        return "next"
    if "이번주" in text or "이번 주" in text:
        return "week"

    if "내일" in text:
        return (date.fromisoformat(today()) + timedelta(days=1)).isoformat()

    if "오늘" in text:
        return today()

    return today()


def detect_time(text):
    """Detect simple Korean time expressions."""
    word_time = detect_korean_word_time(text)

    if word_time:
        return word_time

    match = re.search(r"(오전|오후)?\s*(\d{1,2})\s*시", text)

    if not match:
        return ""

    period = match.group(1) or ""
    hour = int(match.group(2))

    if period == "오후" and hour < 12:
        hour += 12

    if period == "오전" and hour == 12:
        hour = 0

    if period == "" and should_assume_afternoon(text, hour):
        hour += 12

    return f"{hour:02d}:00"


def detect_korean_word_time(text):
    """Detect spoken Korean time expressions such as '오후 세 시'."""
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

    if period == "오전" and hour == 12:
        hour = 0

    if period == "" and should_assume_afternoon(text, hour):
        hour += 12

    return f"{hour:02d}:{minute:02d}"


def should_assume_afternoon(text, hour):
    """Assume PM for casual meeting appointments such as '내일 3시쯤 약속'."""
    if hour < 1 or hour > 6:
        return False

    return contains_any(text, ["약속", "만나", "미팅", "회의", "예약"])


def extract_title(text, action):
    """Extract event title for create/delete/update actions."""
    if action == "list":
        return ""

    cleaned = text

    for token in [
        "오늘",
        "내일",
        "이번주",
        "이번 주",
        "오전",
        "오후",
        "일정",
        "모두",
        "전체",
        "예약해",
        "예약",
        "일정 추가",
        "추가",
        "잡아 줘",
        "잡아줘",
        "등록",
        "등록해",
        "삭제",
        "지워",
        "취소",
        "수정",
        "변경",
        "기억해",
        "알람",
        "알림",
        "해",
    ]:
        cleaned = cleaned.replace(token, " ")

    cleaned = re.split(r"\s*(?:하고|그리고)\s*", cleaned, maxsplit=1)[0]
    cleaned = re.sub(r"\d+\s*분\s*전에\s*알려\s*줘.*$", " ", cleaned)
    cleaned = re.sub(r"\d+\s*시간\s*전에\s*알려\s*줘.*$", " ", cleaned)
    cleaned = re.sub(r"\d+\s*분\s*전\s*알림.*$", " ", cleaned)
    cleaned = re.sub(r"\d+\s*시간\s*전\s*알림.*$", " ", cleaned)
    cleaned = re.sub(r"\d{1,2}\s*시\s*쯤?(?:에)?", " ", cleaned)
    cleaned = re.sub(r"\d{1,2}\s*시", " ", cleaned)
    cleaned = re.sub(
        r"(열두|열하나|열한|열둘|열|아홉|여덟|일곱|여섯|다섯|하나|한|둘|두|셋|세|넷|네)\s*시\s*(?:에)?",
        " ",
        cleaned,
    )
    cleaned = cleanup_calendar_title(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .?!")
    cleaned = cleaned.removeprefix("에 ").strip()
    cleaned = cleaned.removeprefix("에").strip()
    cleaned = re.sub(r"\s*일정$", "", cleaned).strip()

    if action == "delete":
        return cleaned

    return cleaned or fallback_calendar_title(text)


def extract_participants(text):
    """Extract known people mentioned in a Calendar request."""
    normalized = normalize_calendar_text(text)
    people = []

    for person in ["아야", "유이", "유리"]:
        if person in normalized and person not in people:
            people.append(person)

    return people


def cleanup_calendar_title(text):
    """Clean natural calendar title fragments."""
    cleaned = str(text or "")
    cleaned = cleaned.replace("아이 만나", "아야 만나")
    cleaned = cleaned.replace("혜와 만나", "아야 만나")
    cleaned = cleaned.replace("혜랑 만나", "아야 만나")
    cleaned = cleaned.replace("만나기로 약속", "만나기")
    cleaned = cleaned.replace("만나기로", "만나기")
    cleaned = re.sub(r"\s*약속\s*(?:잡아\s*줘|잡아줘)?\s*$", " ", cleaned)
    replacements = {
        "쯤에": " ",
        "쯤": " ",
    }

    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)

    return cleaned


def normalize_calendar_text(text):
    """Normalize STT vocabulary and Calendar-specific artifacts."""
    normalized = normalize_stt_text(text).normalized_text
    normalized = normalized.replace("아이 만나", "아야 만나")
    normalized = normalized.replace("혜와 만나", "아야 만나")
    normalized = normalized.replace("혜랑 만나", "아야 만나")
    normalized = normalized.replace("나의 만나기", "아야 만나기")
    normalized = normalized.replace("나의 만나", "아야 만나")
    return normalize_text(normalized)


def fallback_calendar_title(text):
    """Return a useful generic title when no concrete title was spoken."""
    if "약속" in str(text or ""):
        return "약속"

    return "새 일정"


def contains_any(text, tokens):
    """Return whether any token is present."""
    return any(token in text for token in tokens)


def normalize_text(text):
    """Normalize whitespace."""
    return " ".join(str(text).strip().split())
