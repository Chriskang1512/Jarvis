from dataclasses import asdict, dataclass, field
from datetime import datetime
from uuid import uuid4


MEMORY_SCOPES = ["session", "long_term", "project"]
MEMORY_CATEGORIES = ["profile", "preference", "project", "finance", "hotel", "japanese", "relationship", "general"]


@dataclass(frozen=True)
class MemoryEntry:
    """One persistent Jarvis memory item."""

    id: str
    key: str
    value: str
    category: str = "general"
    scope: str = "long_term"
    created_at: str = ""
    updated_at: str = ""
    source: str = "user"
    confidence: float = 0.75
    event: dict = field(default_factory=dict)

    def __post_init__(self):
        """Fill timestamps for new entries."""
        now = datetime.now().isoformat(timespec="seconds")

        if self.created_at == "":
            object.__setattr__(self, "created_at", now)

        if self.updated_at == "":
            object.__setattr__(self, "updated_at", now)

    def to_dict(self):
        """Return a JSON-serializable dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class MemoryQuery:
    """Normalized Memory Ability request."""

    action: str
    key: str = ""
    value: str = ""
    category: str = "general"
    scope: str = "long_term"
    raw_text: str = ""
    source: str = "user"
    confidence: float = 0.75
    confirmed: bool = False
    event: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryResult:
    """Result payload returned by Memory Ability."""

    action: str
    entry: MemoryEntry | None = None
    entries: list[MemoryEntry] = field(default_factory=list)
    key: str = ""
    message: str = ""
    found: bool = False
    source: str = "canonical"

    def to_natural_language(self):
        """Return a concise Korean response for TTS."""
        if self.message:
            return self.message

        if self.action == "remember" and self.entry is not None:
            return format_saved_message(self.entry)

        if self.action == "recall":
            if self.entry is None:
                return "아직 기억하고 있지 않습니다."

            return format_recall_message(self.entry)

        if self.action == "forget":
            if self.found:
                return "기억에서 삭제했습니다."

            return "삭제할 기억을 찾지 못했습니다."

        if self.action == "list":
            if len(self.entries) == 0:
                return "아직 저장된 기억이 없습니다."

            return "기억하고 있는 내용은 " + ", ".join(entry.key for entry in self.entries) + "입니다."

        return str(self)


def create_memory_entry(query, existing=None):
    """Create or update one MemoryEntry from a query."""
    now = datetime.now().isoformat(timespec="seconds")
    created_at = now if existing is None else existing.created_at
    entry_id = uuid4().hex if existing is None else existing.id

    return MemoryEntry(
        id=entry_id,
        key=query.key,
        value=query.value,
        category=query.category,
        scope=query.scope,
        created_at=created_at,
        updated_at=now,
        source=query.source,
        confidence=query.confidence,
        event=dict(query.event),
    )


def memory_entry_from_dict(data):
    """Create a MemoryEntry from stored JSON data."""
    return MemoryEntry(
        id=str(data.get("id", uuid4().hex)),
        key=str(data.get("key", "")),
        value=str(data.get("value", "")),
        category=str(data.get("category", "general")),
        scope=str(data.get("scope", "long_term")),
        created_at=str(data.get("created_at", "")),
        updated_at=str(data.get("updated_at", "")),
        source=str(data.get("source", "user")),
        confidence=float(data.get("confidence", 0.75)),
        event=dict(data.get("event", {})),
    )


def format_saved_message(entry):
    """Return a save confirmation by scope."""
    if entry.scope == "session":
        return "이번 대화 동안 기억하겠습니다."

    if entry.scope == "project":
        return "Jarvis 프로젝트 기억에 저장했습니다."

    return "장기 기억에 저장했습니다."


def format_recall_message(entry):
    """Return a user-facing recall sentence."""
    if entry.key == "user.name":
        return f"{entry.value}입니다."

    if entry.key == "user.location":
        return f"기본 위치는 {entry.value}입니다."

    if entry.key == "relationship.aya.first_meeting_date":
        return f"{format_korean_date(entry.value)}에 처음 만나셨습니다."

    if entry.key == "relationship.aya.birthday":
        return f"아야 생일은 {format_korean_date(entry.value)}입니다."

    return f"{entry.key}는 {entry.value}입니다."


def format_korean_date(value):
    """Format YYYY-MM-DD as a Korean date string."""
    parts = str(value).split("-")

    if len(parts) != 3:
        return str(value)

    try:
        return f"{int(parts[0])}년 {int(parts[1])}월 {int(parts[2])}일"
    except ValueError:
        return str(value)
