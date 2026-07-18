from dataclasses import dataclass, field


@dataclass(frozen=True)
class CalendarQuery:
    """Normalized Calendar Ability request."""

    date: str = ""
    time: str = ""
    action: str = "list"
    title: str = ""
    description: str = ""
    location: str = ""
    participants: list[str] = field(default_factory=list)
    raw_text: str = ""
    event_id: str = ""
    time_min: object = None
    time_max: object = None
    timezone: str = "Asia/Seoul"
    limit: int | None = None
    order_by: str = "start_time"
