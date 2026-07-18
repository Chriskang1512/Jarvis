import re

from jarvis.abilities.native.memory.models import MemoryQuery
from jarvis.debug_trace import trace_event


REMEMBER_TOKENS = ["기억해", "기억해줘", "저장해", "저장해줘", "앞으로 기억해", "오늘만 기억해"]
FORGET_TOKENS = ["잊어", "잊어줘", "삭제해", "삭제해줘", "기억 지워", "기억에서 지워"]
LIST_TOKENS = ["기억 목록", "뭘 기억", "무엇을 기억", "기억하고 있어", "기억 리스트"]
RECALL_TOKENS = ["뭐야", "무엇", "알고 있어", "기억나", "기억해"]
QUESTION_SUFFIX_TOKENS = ["언제였지", "언제야", "언제", "뭐야", "무엇", "알려줘", "알려 줘", "기억나"]


class MemoryIntentParser:
    """Parse Korean memory commands into MemoryQuery objects."""

    def parse(self, text):
        """Return a normalized MemoryQuery."""
        raw_text = str(text or "").strip()
        normalized_text = normalize_text(raw_text)
        action = detect_action(normalized_text)
        scope = detect_scope(normalized_text)
        category = detect_category(normalized_text)
        key, value = extract_key_value(normalized_text, action)
        event = extract_event_metadata(normalized_text, key, value)
        confidence = score_confidence(action, key, value, normalized_text)
        trace_event("memory.canonical_key", source_text=normalized_text, canonical_key=key)

        return MemoryQuery(
            action=action,
            key=key,
            value=value,
            category=category,
            scope=scope,
            raw_text=raw_text,
            source="user",
            confidence=confidence,
            event=event,
        )


def detect_action(text):
    """Detect the requested memory action."""
    if contains_any(text, LIST_TOKENS):
        return "list"

    if contains_any(text, FORGET_TOKENS):
        return "forget"

    if is_recall_question(text):
        return "recall"

    if contains_any(text, REMEMBER_TOKENS):
        return "remember"

    return "recall"


def detect_scope(text):
    """Detect memory scope from Korean phrases."""
    if "오늘만" in text or "이번 대화" in text or "세션" in text:
        return "session"

    if "프로젝트" in text or "jarvis 프로젝트" in text or "자비스 프로젝트" in text:
        return "project"

    if "앞으로" in text or "장기" in text or "계속" in text:
        return "long_term"

    return "long_term"


def detect_category(text):
    """Detect a coarse memory category."""
    lowered = text.lower()

    if "이름" in lowered or "내 이름" in lowered or "나의 이름" in lowered:
        return "profile"

    if "위치" in lowered or "사는" in lowered or "집" in lowered:
        return "profile"

    if "좋아" in lowered or "선호" in lowered or "싫어" in lowered:
        return "preference"

    if "주식" in lowered or "etf" in lowered or "투자" in lowered:
        return "finance"

    if "호텔" in lowered:
        return "hotel"

    if "일본어" in lowered:
        return "japanese"

    if "프로젝트" in lowered or "jarvis" in lowered or "자비스" in lowered:
        return "project"

    if "아야" in lowered or "처음 만난" in lowered or "첫 만남" in lowered:
        return "relationship"

    return "general"


def extract_key_value(text, action):
    """Extract a standard key and value from text."""
    key = detect_key(text)

    if action == "list":
        return key, ""

    if action in ["recall", "forget"]:
        return key or clean_command_text(text), ""

    value = extract_value_for_key(text, key)

    if key == "":
        key = infer_general_key(text)

    return key, value


def detect_key(text):
    """Return a standard memory key when a phrase is recognized."""
    if "이름" in text:
        return "user.name"

    if "기본 위치" in text or "내 위치" in text or "사는 곳" in text or "집은" in text:
        return "user.location"

    if "jarvis 버전" in text or "자비스 버전" in text:
        return "project.jarvis.version"

    if "좋아하는 etf" in text or "관심 etf" in text:
        return "finance.favorite_etf"

    if "일본어 레벨" in text or "일본어 수준" in text:
        return "japanese.learning_level"

    if is_aya_first_meeting_text(text):
        return "relationship.aya.first_meeting_date"

    if is_aya_birthday_text(text):
        return "relationship.aya.birthday"

    return ""


def extract_value_for_key(text, key):
    """Extract value text for known keys."""
    if key == "user.name":
        patterns = [
            r"내\s*이름은\s*(?P<value>.+?)(?:야|이야|입니다|이다|라고|으로|로|\.|$)",
            r"나는\s*(?P<value>.+?)(?:야|이야|입니다|이다|라고|으로|로|\.|$)",
        ]
        return first_regex_value(patterns, text)

    if key == "user.location":
        patterns = [
            r"기본\s*위치는\s*(?P<value>.+?)(?:야|이야|입니다|이다|\.|$)",
            r"나는\s*(?P<value>.+?)에\s*살",
            r"내\s*위치는\s*(?P<value>.+?)(?:야|이야|입니다|이다|\.|$)",
        ]
        return first_regex_value(patterns, text)

    if key == "relationship.aya.first_meeting_date":
        date_value = extract_date_iso(text)

        if date_value != "":
            return date_value

        return clean_value(clean_command_text(text))

    if key == "relationship.aya.birthday":
        date_value = extract_date_iso(text)

        if date_value != "":
            return date_value

        return clean_value(clean_command_text(text))

    cleaned = clean_command_text(text)

    if "은 " in cleaned:
        return clean_value(cleaned.split("은 ", 1)[1])

    if "는 " in cleaned:
        return clean_value(cleaned.split("는 ", 1)[1])

    return cleaned


def first_regex_value(patterns, text):
    """Return the first named regex value."""
    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return clean_value(match.group("value"))

    return clean_value(clean_command_text(text))


def infer_general_key(text):
    """Infer a general key when no standard key matched."""
    cleaned = clean_command_text(text)

    if "은 " in cleaned:
        return slug_key(cleaned.split("은 ", 1)[0])

    if "는 " in cleaned:
        return slug_key(cleaned.split("는 ", 1)[0])

    return slug_key(cleaned[:32])


def clean_command_text(text):
    """Remove memory command tokens from a phrase."""
    cleaned = text

    for token in REMEMBER_TOKENS + FORGET_TOKENS:
        cleaned = cleaned.replace(token, "")

    for token in QUESTION_SUFFIX_TOKENS:
        cleaned = cleaned.replace(token, "")

    for token in ["앞으로", "오늘만", "장기 기억에", "장기", "프로젝트에서", "jarvis 프로젝트에서", "자비스 프로젝트에서"]:
        cleaned = cleaned.replace(token, "")

    return clean_value(cleaned)


def is_aya_first_meeting_text(text):
    """Return whether text refers to the first meeting with Aya."""
    return "아야" in text and ("처음 만난" in text or "처음 만난 날" in text or "첫 만남" in text or "처음 만난 게" in text)


def is_aya_birthday_text(text):
    """Return whether text refers to Aya's birthday."""
    return "아야" in text and "생일" in text


def extract_event_metadata(text, key, value):
    """Extract optional event metadata for future time-aware memory."""
    if key == "relationship.aya.birthday":
        date_value = value if is_iso_date(value) else extract_date_iso(text)
        event = {
            "type": "event",
            "title": "아야 생일",
            "people": ["아야"],
            "date": date_value,
            "location": "",
            "note": clean_command_text(text),
        }

        return {key: value for key, value in event.items() if value not in ["", []]}

    if key != "relationship.aya.first_meeting_date":
        return {}

    date_value = value if is_iso_date(value) else extract_date_iso(text)
    event = {
        "type": "event",
        "title": "아야와 처음 만난 날",
        "people": ["아야"],
        "date": date_value,
        "location": "",
        "note": clean_command_text(text),
    }

    return {key: value for key, value in event.items() if value not in ["", []]}


def extract_date_iso(text):
    """Extract a Korean date phrase as YYYY-MM-DD."""
    match = re.search(r"(?P<year>\d{4})\s*년\s*(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일", text)

    if not match:
        match = re.search(r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})", text)

    if not match:
        return ""

    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    return f"{year:04d}-{month:02d}-{day:02d}"


def is_iso_date(value):
    """Return whether value is YYYY-MM-DD."""
    return re.match(r"^\d{4}-\d{2}-\d{2}$", str(value)) is not None


def clean_value(value):
    """Clean extracted key/value text."""
    cleaned = str(value).strip()
    cleaned = cleaned.strip(".?! ")

    for suffix in ["입니다", "이야", "이다", "야", "라고", "으로", "로"]:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()

    return cleaned


def slug_key(text):
    """Create a simple general memory key."""
    cleaned = re.sub(r"\s+", "_", clean_value(text))
    cleaned = re.sub(r"[^\w가-힣_.-]", "", cleaned)
    return f"general.{cleaned}" if cleaned else "general.memory"


def is_recall_question(text):
    """Return whether text asks to recall memory."""
    if is_aya_first_meeting_text(text) and contains_any(text, ["언제", "언제야", "언제였지", "알려"]):
        return True

    if is_aya_birthday_text(text) and contains_any(text, ["언제", "언제야", "언제였지", "알려", "기억나"]):
        return True

    if "내 이름" in text and contains_any(text, ["뭐", "무엇", "알려"]):
        return True

    if contains_any(text, ["뭐야", "무엇", "기억나", "언제", "언제야"]):
        return True

    return False


def score_confidence(action, key, value, text):
    """Return a simple parser confidence score."""
    if action == "remember" and key and value:
        return 0.96

    if action in ["recall", "forget"] and key:
        return 0.9

    if action == "list":
        return 0.9

    if "기억" in text:
        return 0.72

    return 0.5


def contains_any(text, tokens):
    """Return whether any token appears in text."""
    return any(token in text for token in tokens)


def normalize_text(text):
    """Normalize whitespace and polite spacing."""
    return " ".join(str(text).strip().split())
