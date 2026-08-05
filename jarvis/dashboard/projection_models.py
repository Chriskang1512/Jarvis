"""Immutable CQRS read models for Dashboard Runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from jarvis.runtime.state import RuntimeState


CURRENT_PROJECTION_SCHEMA_VERSION = 1


def utc_now():
    return datetime.now(timezone.utc)


class ProjectionHealthStatus(str, Enum):
    HEALTHY = "Healthy"
    LAG = "Lag"
    REBUILDING = "Rebuilding"
    FAILED = "Failed"


@dataclass(frozen=True)
class ProjectionVersion:
    projection_id: str
    schema_version: int = CURRENT_PROJECTION_SCHEMA_VERSION
    generated_at: datetime = field(default_factory=utc_now)
    runtime_version: str = "v1.5"


@dataclass(frozen=True)
class TimelineView:
    event_sequence: int
    event_type: str
    occurred_at: datetime
    session_id: str
    node_id: str = ""
    status: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True)
class NodeView:
    node_id: str
    node_type: str = ""
    status: str = "Pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    retry_count: int = 0
    provider: str = ""
    ability: str = ""
    artifact_ids: tuple[str, ...] = ()
    memory_ids: tuple[str, ...] = ()

    @property
    def elapsed_seconds(self):
        if not self.started_at:
            return 0.0
        end = self.finished_at or utc_now()
        return max(0.0, (end - self.started_at).total_seconds())


@dataclass(frozen=True)
class RuntimeSessionView:
    session_id: str
    goal: str = ""
    status: str = "Running"
    started_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None
    planner_status: str = "Pending"
    execution_status: str = "Pending"
    verification_status: str = "Pending"
    memory_status: str = "Pending"
    artifact_status: str = "Pending"
    retry_count: int = 0
    waiting_permission: bool = False
    current_node: str = ""
    current_runtime_state: RuntimeState = RuntimeState.IDLE
    nodes: Mapping[str, NodeView] = field(default_factory=dict)
    timeline: tuple[TimelineView, ...] = ()
    last_event_sequence: int = 0
    projection_version: ProjectionVersion | None = None

    def __post_init__(self):
        object.__setattr__(self, "current_runtime_state", RuntimeState(self.current_runtime_state))
        object.__setattr__(self, "nodes", MappingProxyType(dict(self.nodes)))
        object.__setattr__(self, "timeline", tuple(self.timeline))

    @property
    def elapsed_seconds(self):
        end = self.completed_at or utc_now()
        return max(0.0, (end - self.started_at).total_seconds())


@dataclass(frozen=True)
class ProjectionHealth:
    status: ProjectionHealthStatus
    last_event_sequence: int
    expected_event_sequence: int
    lag: int
    updated_at: datetime = field(default_factory=utc_now)
    error_type: str = ""


@dataclass(frozen=True)
class DashboardProjectionSnapshot:
    snapshot_id: str
    projection_version: ProjectionVersion
    last_event_sequence: int
    sessions: tuple[RuntimeSessionView, ...]
    created_at: datetime = field(default_factory=utc_now)
