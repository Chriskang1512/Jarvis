"""Calendar query polish filters shared by providers."""


def apply_calendar_query_filters(events, query):
    """Return events filtered by display scope and positional hints."""
    filtered = list(events or [])
    time_scope = str(getattr(query, "time_scope", "") or "").strip()

    if time_scope:
        filtered = [event for event in filtered if event_matches_time_scope(event, time_scope)]

    position = str(getattr(query, "position", "") or "").strip()

    if position == "first":
        return filtered[:1]

    if position == "last":
        return filtered[-1:] if filtered else []

    return filtered


def event_matches_time_scope(event, time_scope):
    """Return whether an event is in a coarse day period."""
    value = str(getattr(event, "time", "") or "").strip()

    if value == "":
        return False

    try:
        hour = int(value.split(":", 1)[0])
    except ValueError:
        return False

    if time_scope == "morning":
        return 0 <= hour < 12

    if time_scope == "afternoon":
        return 12 <= hour < 18

    if time_scope == "evening":
        return 18 <= hour < 24

    return True


def ambiguous_calendar_result(query, provider_name, action, matches):
    """Return an ambiguity result when a destructive mutation has many targets."""
    from jarvis.abilities.native.calendar.result import CalendarResult

    return CalendarResult(
        success=False,
        action=action,
        events=list(matches or []),
        count=len(list(matches or [])),
        provider=provider_name,
        date=str(getattr(query, "date", "") or ""),
        error_code="AMBIGUOUS_EVENT",
        message=ambiguous_calendar_message(action, matches),
    )


def ambiguous_calendar_message(action, matches):
    """Return a safe clarification for ambiguous update/delete targets."""
    verb = "수정" if action == "update" else "삭제"
    lines = [f"같은 조건의 일정이 {len(list(matches or []))}건 있습니다. 어떤 일정을 {verb}할까요?"]

    for index, event in enumerate(list(matches or [])[:5], start=1):
        label = event_label(event)
        lines.append(f"{index}. {label}")

    return "\n".join(lines)


def event_label(event):
    """Return a compact event label for clarification."""
    date_value = str(getattr(event, "date", "") or "")
    time_value = str(getattr(event, "time", "") or "")
    title = str(getattr(event, "title", "") or "일정")

    if time_value:
        return f"{date_value} {time_value} {title}".strip()

    return f"{date_value} 종일 {title}".strip()
