import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class ResolvedDate:
    """One normalized local date expression shared by abilities."""

    start_date: str
    end_date: str
    kind: str
    source_text: str = ""
    confidence: float = 1.0

    @property
    def is_range(self):
        return self.start_date != self.end_date


class DateResolver:
    """Resolve common Korean, English, and Japanese local date expressions."""

    def __init__(self, today_provider=None):
        self.today_provider = today_provider or date.today

    def resolve(self, text, reference_date=None):
        raw = str(text or "")
        normalized = " ".join(raw.strip().lower().split())
        current = reference_date or self.today_provider()
        if isinstance(current, datetime):
            current = current.date()

        relative = (
            (("day after tomorrow", "\ubaa8\ub808", "\u660e\u5f8c\u65e5", "\u3042\u3055\u3063\u3066"), 2, "day_after_tomorrow"),
            (("tomorrow", "\ub0b4\uc77c", "\u660e\u65e5", "\u3042\u3057\u305f"), 1, "tomorrow"),
            (("today", "\uc624\ub298", "\u4eca\u65e5", "\u304d\u3087\u3046"), 0, "today"),
        )
        for tokens, offset, kind in relative:
            if any(token in normalized for token in tokens):
                target = current + timedelta(days=offset)
                return ResolvedDate(target.isoformat(), target.isoformat(), kind, raw)

        if any(token in normalized for token in ("\uc8fc\ub9d0", "weekend", "\u9031\u672b")):
            saturday = current + timedelta(days=(5 - current.weekday()) % 7)
            return ResolvedDate(
                saturday.isoformat(),
                (saturday + timedelta(days=1)).isoformat(),
                "weekend",
                raw,
            )

        if any(token in normalized for token in ("\uc774\ubc88\uc8fc", "\uc774\ubc88 \uc8fc", "this week", "\u4eca\u9031")):
            start = current - timedelta(days=current.weekday())
            end = start + timedelta(days=6)
            return ResolvedDate(start.isoformat(), end.isoformat(), "this_week", raw)

        weekday = _resolve_next_weekday(normalized, current)
        if weekday is not None:
            return ResolvedDate(weekday.isoformat(), weekday.isoformat(), "weekday", raw)

        explicit = re.search(r"(?<!\d)(\d{1,2})\s*(?:\uc6d4|month)\s*(\d{1,2})\s*(?:\uc77c|day)?", normalized)
        if explicit:
            month, day = map(int, explicit.groups())
            year = current.year
            try:
                target = date(year, month, day)
                if target < current:
                    target = date(year + 1, month, day)
                return ResolvedDate(target.isoformat(), target.isoformat(), "explicit", raw)
            except ValueError:
                return None
        return None


def _resolve_next_weekday(text, current):
    names = {
        "\uc6d4\uc694\uc77c": 0,
        "\ud654\uc694\uc77c": 1,
        "\uc218\uc694\uc77c": 2,
        "\ubaa9\uc694\uc77c": 3,
        "\uae08\uc694\uc77c": 4,
        "\ud1a0\uc694\uc77c": 5,
        "\uc77c\uc694\uc77c": 6,
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
        "\u6708\u66dc\u65e5": 0,
        "\u706b\u66dc\u65e5": 1,
        "\u6c34\u66dc\u65e5": 2,
        "\u6728\u66dc\u65e5": 3,
        "\u91d1\u66dc\u65e5": 4,
        "\u571f\u66dc\u65e5": 5,
        "\u65e5\u66dc\u65e5": 6,
    }
    for name, target_weekday in names.items():
        if name not in text:
            continue
        delta = (target_weekday - current.weekday()) % 7
        if any(token in text for token in ("\ub2e4\uc74c\uc8fc", "next week", "\u6765\u9031")):
            delta = (7 - current.weekday()) + target_weekday
        elif delta == 0:
            delta = 7
        return current + timedelta(days=delta)
    return None
