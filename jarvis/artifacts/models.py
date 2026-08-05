"""Provider-neutral immutable artifact contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


CURRENT_ARTIFACT_SCHEMA_VERSION = 1


def utc_now():
    return datetime.now(timezone.utc)


class ArtifactType(str, Enum):
    MAIL = "Mail"
    CALENDAR_EVENT = "CalendarEvent"
    FILE = "File"
    PDF = "Pdf"
    IMAGE = "Image"
    AUDIO = "Audio"
    VIDEO = "Video"
    DOCUMENT = "Document"
    TEXT = "Text"
    CLIPBOARD = "Clipboard"
    CUSTOM = "Custom"


class ArtifactStatus(str, Enum):
    CREATED = "Created"
    UPDATED = "Updated"
    ARCHIVED = "Archived"
    DELETED = "Deleted"


class ArtifactVisibility(str, Enum):
    PRIVATE = "Private"
    SESSION = "Session"
    USER = "User"
    SYSTEM = "System"


class ArtifactRetentionClass(str, Enum):
    TRANSIENT = "Transient"
    STANDARD = "Standard"
    LONG_TERM = "LongTerm"
    PERMANENT = "Permanent"


@dataclass(frozen=True)
class ArtifactProvenance:
    created_by: str
    provider: str
    execution_id: str
    node_id: str
    timestamp: datetime = field(default_factory=utc_now)
    derived_from: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "derived_from", tuple(self.derived_from))


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    artifact_type: ArtifactType
    provider: str
    title: str
    summary: str
    created_at: datetime
    updated_at: datetime
    owner: str
    tags: tuple[str, ...]
    status: ArtifactStatus
    source_goal_id: str
    source_execution_id: str
    parent_artifact_id: str
    child_artifact_ids: tuple[str, ...]
    external_resource_id: str
    checksum: str
    retention_class: ArtifactRetentionClass
    visibility: ArtifactVisibility
    schema_version: int
    produced_by_capability: str
    produced_by_provider: str
    produced_by_ability_version: str
    provenance: ArtifactProvenance
    uri: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.artifact_id or self.schema_version < 1:
            raise ValueError("Artifact ID and positive schema version are required.")
        if not self.checksum:
            raise ValueError("Artifact checksum is required.")
        object.__setattr__(self, "artifact_type", ArtifactType(self.artifact_type))
        object.__setattr__(self, "status", ArtifactStatus(self.status))
        object.__setattr__(self, "visibility", ArtifactVisibility(self.visibility))
        object.__setattr__(
            self, "retention_class", ArtifactRetentionClass(self.retention_class)
        )
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "child_artifact_ids", tuple(self.child_artifact_ids))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class ArtifactBuildRequest:
    artifact_type: ArtifactType
    title: str
    source_goal_id: str
    source_execution_id: str
    node_id: str
    output_key: str
    produced_by_capability: str
    provider: str = ""
    ability_version: str = ""
    summary: str = ""
    owner: str = ""
    tags: tuple[str, ...] = ()
    parent_artifact_id: str = ""
    derived_from: tuple[str, ...] = ()
    external_resource_id: str = ""
    checksum: str = ""
    uri: str = ""
    retention_class: ArtifactRetentionClass = ArtifactRetentionClass.STANDARD
    visibility: ArtifactVisibility = ArtifactVisibility.PRIVATE
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactSearchResult:
    artifact: ArtifactRef
    score: float
    matched_fields: tuple[str, ...]
