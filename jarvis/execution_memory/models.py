"""Immutable contracts for versioned execution experience memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


CURRENT_EXECUTION_MEMORY_SCHEMA_VERSION = 1
CURRENT_EXECUTION_SUMMARY_VERSION = 1


def utc_now():
    return datetime.now(timezone.utc)


class MemoryFactType(str, Enum):
    FACT = "Fact"
    DERIVED = "Derived"
    INFERRED = "Inferred"
    USER_PROVIDED = "UserProvided"
    SYSTEM_OBSERVED = "SystemObserved"


class HistoryType(str, Enum):
    GOAL = "Goal"
    EXECUTION = "Execution"
    VERIFICATION = "Verification"
    RETRY = "Retry"
    REPLAN = "Replan"
    PERMISSION = "Permission"
    FAILURE = "Failure"


class RetentionClass(str, Enum):
    TRANSIENT = "Transient"
    STANDARD = "Standard"
    LONG_TERM = "LongTerm"
    PERMANENT = "Permanent"


@dataclass(frozen=True)
class MemoryRetentionPolicy:
    retention_class: RetentionClass = RetentionClass.STANDARD
    expires_at: datetime | None = None
    archive_after_days: int | None = None
    allow_automatic_deletion: bool = False


@dataclass(frozen=True)
class MemoryProvenance:
    source_type: MemoryFactType
    source_execution_id: str
    source_node_id: str = ""
    source_provider: str = ""
    generated_at: datetime = field(default_factory=utc_now)
    derived_from: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryConfidence:
    factual_confidence: float
    retrieval_confidence: float
    verification_status: str


@dataclass(frozen=True)
class SessionReplayReference:
    session_id: str
    event_range: tuple[int, int]
    journal_reference: str
    available: bool
    retention_class: RetentionClass


@dataclass(frozen=True)
class HistoryEntry:
    history_type: HistoryType
    status: str
    node_id: str = ""
    capability_id: str = ""
    occurred_at: datetime = field(default_factory=utc_now)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(
            self, "metadata", MappingProxyType(dict(self.metadata))
        )


@dataclass(frozen=True)
class ExecutionMemoryRecord:
    schema_version: int
    summary_version: int
    record_id: str
    source_execution_id: str
    goal_id: str
    session_id: str
    snapshot_id: str
    graph_id: str
    goal_signature: str
    outcome: str
    result_hash: str
    histories: tuple[HistoryEntry, ...]
    replay_reference: SessionReplayReference
    provenance: MemoryProvenance
    confidence: MemoryConfidence
    retention_class: RetentionClass = RetentionClass.STANDARD
    retention_policy: MemoryRetentionPolicy = field(
        default_factory=MemoryRetentionPolicy
    )
    tags: tuple[str, ...] = ()
    redacted_metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self):
        object.__setattr__(self, "histories", tuple(self.histories))
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(
            self,
            "redacted_metadata",
            MappingProxyType(dict(self.redacted_metadata)),
        )

    @property
    def unique_key(self):
        return f"{self.source_execution_id}:{self.summary_version}"


@dataclass(frozen=True)
class MemorySearchResult:
    record: ExecutionMemoryRecord
    score: float
    matched_fields: tuple[str, ...]
    provenance: MemoryProvenance
    verification_status: str


@dataclass(frozen=True)
class PlannerHint:
    """Sprint 1 contract only. This model is not injected into Planner."""

    hint_id: str
    query_goal_id: str
    source_memory_ids: tuple[str, ...]
    hint_type: str
    summary: str
    reusable_patterns: tuple[str, ...] = ()
    known_failures: tuple[str, ...] = ()
    known_successful_steps: tuple[str, ...] = ()
    required_revalidation: tuple[str, ...] = ()
    capability_snapshot_reference: str = ""
    confidence: float = 0.0
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
