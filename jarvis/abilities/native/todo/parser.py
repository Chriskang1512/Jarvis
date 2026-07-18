"""Todo intent parser."""

import re
from dataclasses import replace
from datetime import datetime, timedelta

from jarvis.abilities.native.todo.query import TodoQuery
from jarvis.core.todos.todo import TODO_ACTIVE, TODO_COMPLETED


class TodoIntentParser:
    """Parse Korean Todo commands."""

    def parse(self, text):
        """Return TodoQuery."""
        raw_text = str(text or "").strip()
        normalized = normalize_text(raw_text)

        if is_list_completed(normalized):
            return TodoQuery(action="list", status=TODO_COMPLETED, raw_text=raw_text)

        if is_list(normalized):
            return TodoQuery(
                action="list",
                status=parse_target_status(normalized),
                date_scope=parse_date_scope(normalized),
                raw_text=raw_text,
            )

        if is_delete(normalized):
            return TodoQuery(
                action="delete",
                title=parse_delete_title(normalized),
                status=parse_target_status(normalized),
                raw_text=raw_text,
            )

        if is_complete(normalized):
            return TodoQuery(
                action="complete",
                todo_id=parse_ordinal_reference(normalized),
                title=parse_title_reference(normalized),
                raw_text=raw_text,
            )

        if is_restore(normalized):
            return TodoQuery(action="restore", title=parse_title_reference(normalized), raw_text=raw_text)

        if is_create(normalized):
            return TodoQuery(
                action="create",
                title=parse_create_title(normalized),
                due_at=parse_due_at(normalized),
                raw_text=raw_text,
            )

        return TodoQuery(action="list", raw_text=raw_text)


def normalize_query(input_data, parser=None):
    """Return TodoQuery from dict/object/text."""
    if hasattr(input_data, "action") and hasattr(input_data, "title"):
        return input_data

    if isinstance(input_data, dict) and "action" in input_data:
        query = TodoQuery(
            action=str(input_data.get("action", "list")),
            todo_id=str(input_data.get("todo_id", "")),
            title=str(input_data.get("title", "")),
            due_at=str(input_data.get("due_at", input_data.get("datetime", ""))),
            priority=str(input_data.get("priority", "normal")),
            status=normalize_status(input_data.get("status", "")),
            date_scope=str(input_data.get("date_scope", "")),
            confirmed=bool(input_data.get("_confirmed", input_data.get("confirmed", False))),
            raw_text=str(input_data.get("raw_text", input_data.get("text", ""))),
        )
        return enrich_query_reference(query, parser or TodoIntentParser())

    raw_text = input_data.get("text", "") if isinstance(input_data, dict) else str(input_data or "")
    query = (parser or TodoIntentParser()).parse(raw_text)

    if isinstance(input_data, dict) and bool(input_data.get("_confirmed", input_data.get("confirmed", False))):
        return replace(query, confirmed=True)

    return query


def enrich_query_reference(query, parser):
    """Fill target references from raw text when AI/parser output omitted them."""
    if query.action not in {"complete", "delete", "update", "restore"}:
        return query

    title_ordinal = parse_ordinal_reference(query.title)

    if title_ordinal:
        return replace(query, todo_id=query.todo_id or title_ordinal, title="")

    if query.todo_id or query.title or query.status:
        return query

    raw_text = str(query.raw_text or "")

    if raw_text == "":
        return query

    parsed = parser.parse(raw_text)
    return replace(
        query,
        todo_id=parsed.todo_id or query.todo_id,
        title=parsed.title or query.title,
        status=parsed.status or query.status,
    )


def is_create(text):
    """Return whether text creates a todo."""
    create_tokens = ["추가", "등록", "저장", "넣어", "넣어줘", "넣어 줘", "해야 할 일", "할 일"]
    return any(token in text for token in create_tokens) and not is_list(text)


def is_list(text):
    """Return whether text lists todos."""
    has_todo_subject = any(token in text for token in ["할 일", "할일", "투두", "해야 할 일"])
    has_list_verb = any(token in text for token in ["알려", "보여", "목록", "뭐", "무엇"])
    return has_todo_subject and has_list_verb


def is_list_completed(text):
    """Return whether text lists completed todos."""
    return is_list(text) and any(token in text for token in ["끝난", "완료", "끝낸"])


def is_complete(text):
    """Return whether text completes a todo."""
    return any(token in text for token in ["완료", "끝냈", "끝났", "처리했", "했어"])


def is_delete(text):
    """Return whether text deletes/cancels a todo."""
    return any(token in text for token in ["삭제", "지워", "취소"])


def is_restore(text):
    """Return whether text restores a todo."""
    return any(token in text for token in ["복원", "되살려"])


def parse_create_title(text):
    """Extract create title."""
    value = remove_due_phrase(text)
    value = re.sub(
        r"\s*(해야 할 일|할 일)?\s*(추가해|추가|등록해|등록|저장해|저장|넣어 줘|넣어줘|넣어|해 줘|해줘)$",
        "",
        value,
    ).strip()
    value = re.sub(r"^(오늘|내일)\s*", "", value).strip()
    return normalize_title(value)


def parse_delete_title(text):
    """Extract title for delete/update phrasing."""
    if parse_target_status(text):
        return ""

    if normalize_title(re.sub(r"(\uc0ad\uc81c|\uc9c0\uc6cc|\ucde8\uc18c).*", "", text)) in {"\ud560 \uc77c", "\ud560\uc77c", "\ud22c\ub450"}:
        return ""

    match = re.search(r"(?P<title>.+?)에서\s*(?P<item>.+?)\s*(?:삭제|지워|취소)", text)
    if match:
        return normalize_title(f"{match.group('title')} {match.group('item')}")

    return normalize_title(re.sub(r"(삭제|지워|취소).*", "", text))


def parse_target_status(text):
    """Return a target status for bulk status commands."""
    if any(token in text for token in ["완료된", "완료한", "끝난", "끝낸"]):
        return TODO_COMPLETED

    if any(token in text for token in ["진행 중", "진행중", "안 끝난", "미완료"]):
        return TODO_ACTIVE

    return ""


def parse_title_reference(text):
    """Extract title reference."""
    ordinal = parse_ordinal_reference(text)

    if ordinal:
        return ""

    return normalize_title(re.sub(r"(완료.*|끝냈.*|끝났.*|처리했.*|했어.*|복원.*|되살려.*)", "", text))


def parse_ordinal_reference(text):
    """Return ordinal reference key."""
    indexes = parse_ordinal_indexes(text)

    if len(indexes) == 1:
        return f"ordinal:{indexes[0]}"

    if len(indexes) > 1:
        return "ordinals:" + ",".join(str(index) for index in indexes)

    return ""


def parse_ordinal_indexes(text):
    """Return one-based ordinal indexes mentioned in text."""
    value = normalize_text(text)
    indexes = []

    for match in re.finditer(r"(\d+)\s*번(?:째)?", value):
        indexes.append(int(match.group(1)))

    word_patterns = (
        (1, r"(첫\s*번째|첫번째|첫\s*번째\s*거|첫번째거|일\s*번|첫\s*할\s*일)"),
        (2, r"(두\s*번째|두번째|두\s*번째\s*거|두번째거|이\s*번)"),
        (3, r"(세\s*번째|세번째|세\s*번째\s*거|세번째거|삼\s*번)"),
    )

    for index, pattern in word_patterns:
        if re.search(pattern, value):
            indexes.append(index)

    unique = []

    for index in indexes:
        if index > 0 and index not in unique:
            unique.append(index)

    return tuple(unique)


def normalize_status(value):
    """Normalize status strings from rule and AI parsers."""
    text = str(value or "").strip().lower()

    if text in {"completed", "complete", "done", TODO_COMPLETED.lower()}:
        return TODO_COMPLETED

    if text in {"active", "pending", "open", TODO_ACTIVE.lower()}:
        return TODO_ACTIVE

    return str(value or "")


def parse_date_scope(text):
    """Return date scope."""
    if "내일" in text:
        return "tomorrow"
    if "오늘" in text:
        return "today"
    return ""


def parse_due_at(text):
    """Parse a simple Korean due datetime."""
    date_value = ""
    today = datetime.now().date()

    if "내일" in text:
        date_value = (today + timedelta(days=1)).isoformat()
    elif "오늘" in text:
        date_value = today.isoformat()

    time_value = parse_time(text)

    if date_value and time_value:
        return f"{date_value}T{time_value}:00"

    return ""


def parse_time(text):
    """Parse simple hour text."""
    word_time = parse_korean_word_time(text)

    if word_time:
        return word_time

    match = re.search(r"(오전|오후)?\s*(\d{1,2})\s*시", text)

    if not match:
        return ""

    hour = int(match.group(2))
    period = match.group(1) or ""

    if period == "오후" and hour < 12:
        hour += 12
    if period == "오전" and hour == 12:
        hour = 0

    return f"{hour:02d}:00"


def parse_korean_word_time(text):
    """Parse Korean spoken clock words such as '오후 다섯 시'."""
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
    pattern = (
        r"(오전|오후)?\s*"
        r"(열두|열하나|열한|열둘|열|아홉|여덟|일곱|여섯|다섯|하나|한|둘|두|셋|세|넷|네)"
        r"\s*시"
    )
    match = re.search(pattern, normalized)

    if not match:
        return ""

    period = match.group(1) or ""
    hour = hour_words.get(match.group(2), 0)

    if hour <= 0:
        return ""

    if period == "오후" and hour < 12:
        hour += 12
    if period == "오전" and hour == 12:
        hour = 0

    return f"{hour:02d}:00"


def remove_due_phrase(text):
    """Remove date/time phrase from title candidate."""
    value = re.sub(r"(오늘|내일)?\s*(오전|오후)?\s*\d{1,2}\s*시에?\s*", "", text).strip()
    value = re.sub(
        r"(오늘|내일)?\s*(오전|오후)?\s*(열두|열하나|열한|열둘|열|아홉|여덟|일곱|여섯|다섯|하나|한|둘|두|셋|세|넷|네)\s*시에?\s*",
        "",
        value,
    )
    return value.strip()


def normalize_title(value):
    """Normalize title."""
    return " ".join(str(value or "").strip().split())


def normalize_text(value):
    """Normalize text."""
    return " ".join(str(value or "").strip().split())
