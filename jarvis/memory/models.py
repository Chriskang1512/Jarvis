"""Typed contracts for the Sprint 20 Memory System."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class MemoryType(str, Enum):
    WORKING = "working"
    LONG_TERM = "long_term"
    PREFERENCE = "preference"
    PERSONAL_LEXICON = "personal_lexicon"
    CORRECTION = "correction"
    ENTITY_GRAPH = "entity_graph"


@dataclass(frozen=True)
class MemoryRecord:
    key: str
    value: str
    memory_type: MemoryType
    scope: str = "user"
    session_id: str = ""
    source: str = "user"
    source_provider: str = ""
    created_by: str = "user"
    confidence: float = 1.0
    expires_at: str = ""
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self):
        payload = asdict(self)
        payload["memory_type"] = self.memory_type.value
        payload["provider"] = self.source_provider
        return payload


@dataclass(frozen=True)
class MemoryContext:
    records: tuple[MemoryRecord, ...] = ()

    def get(self, key, default=""):
        for record in self.records:
            if record.key == key:
                return record.value
        return default

    def preferences(self):
        return {
            record.key: record.value
            for record in self.records
            if record.memory_type == MemoryType.PREFERENCE
        }


@dataclass(frozen=True)
class StoreDecision:
    should_store: bool
    reason: str
    memory_type: MemoryType | None = None
    key: str = ""
    value: str = ""
    confidence: float = 0.0
