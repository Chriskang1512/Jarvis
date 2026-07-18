"""Google Calendar provider models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class GoogleCalendarListWindow:
    """Absolute Google Calendar list window."""

    time_min: datetime
    time_max: datetime | None
    timezone: str = "Asia/Seoul"
    limit: int | None = 10
    order_by: str = "startTime"
