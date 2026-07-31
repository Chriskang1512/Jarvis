"""Immutable audit identity for a validated execution plan."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar, Mapping
from uuid import uuid4

from jarvis.native_task_graph import NativeTaskGraphSerializer
from jarvis.native_task_graph.models import deep_freeze, mutable_projection


PLANNER_METADATA_KEYS = (
    "capabilitySnapshotId",
    "registryHash",
    "plannerType",
    "plannerVersion",
    "planningPolicyVersion",
)


@dataclass(frozen=True)
class ExecutionPlanSnapshot:
    SNAPSHOT_VERSION: ClassVar[str] = "1.0"
    SCHEMA_VERSION: ClassVar[str] = "1.0"

    graph_hash: str
    planner_metadata: Mapping[str, str]
    planning_confidence: float
    snapshot_id: str = field(
        default_factory=lambda: f"execution-plan-{uuid4()}"
    )
    validation_hash: str = ""
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self):
        if not self.graph_hash or not self.validation_hash:
            raise ValueError("GraphHash and ValidationHash are required.")
        if not 0.0 <= self.planning_confidence <= 1.0:
            raise ValueError("PlanningConfidence must be between 0 and 1.")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("CreatedAt must be timezone-aware.")
        metadata = dict(self.planner_metadata)
        missing = [
            key for key in PLANNER_METADATA_KEYS if not metadata.get(key)
        ]
        if missing:
            raise ValueError(
                "PlannerMetadata is missing: " + ", ".join(missing)
            )
        object.__setattr__(
            self,
            "planner_metadata",
            deep_freeze(
                {key: str(metadata[key]) for key in PLANNER_METADATA_KEYS}
            ),
        )

    def to_dict(self):
        return {
            "graphHash": self.graph_hash,
            "plannerMetadata": mutable_projection(
                self.planner_metadata
            ),
            "planningConfidence": self.planning_confidence,
            "snapshotId": self.snapshot_id,
            "validationHash": self.validation_hash,
            "createdAt": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            graph_hash=str(value["graphHash"]),
            planner_metadata=dict(value["plannerMetadata"]),
            planning_confidence=float(value["planningConfidence"]),
            snapshot_id=str(value["snapshotId"]),
            validation_hash=str(value["validationHash"]),
            created_at=datetime.fromisoformat(
                str(value["createdAt"]).replace("Z", "+00:00")
            ),
        )


class ExecutionPlanSnapshotFactory:
    def __init__(self, validator):
        self.validator = validator

    def create(
        self,
        planner_result,
        capability_snapshot,
        *,
        goal,
        mappings=(),
        max_nodes=None,
    ):
        graph = planner_result.graph
        if graph is None:
            raise ValueError("A planned graph is required.")
        report = self.validator.validate(
            graph,
            capability_snapshot,
            goal=goal,
            mappings=mappings,
            max_nodes=max_nodes,
        )
        if not report.is_valid:
            raise ValueError(
                "ExecutionPlanSnapshot requires a valid graph."
            )
        return ExecutionPlanSnapshot(
            graph_hash=canonical_hash(
                NativeTaskGraphSerializer.to_dict(graph)
            ),
            planner_metadata={
                key: graph.metadata.get(key, "")
                for key in PLANNER_METADATA_KEYS
            },
            planning_confidence=float(planner_result.confidence),
            validation_hash=canonical_hash(
                validation_projection(report)
            ),
        )


@dataclass(frozen=True)
class SnapshotVerificationIssue:
    code: str
    message: str


@dataclass(frozen=True)
class SnapshotVerificationResult:
    is_valid: bool
    issues: tuple[SnapshotVerificationIssue, ...] = ()


class SnapshotVerifier:
    """Fail-closed integrity gate before GraphExecutionSession creation."""

    def verify(
        self,
        snapshot,
        graph,
        validation_report,
        *,
        snapshot_version=ExecutionPlanSnapshot.SNAPSHOT_VERSION,
        schema_version=ExecutionPlanSnapshot.SCHEMA_VERSION,
    ):
        issues = []

        if snapshot_version != ExecutionPlanSnapshot.SNAPSHOT_VERSION:
            issues.append(
                SnapshotVerificationIssue(
                    "snapshot_version_unsupported",
                    f"Unsupported SnapshotVersion: {snapshot_version}",
                )
            )

        graph_payload = NativeTaskGraphSerializer.to_dict(graph)
        actual_schema_version = str(
            graph_payload.get("schemaVersion", "")
        )
        if (
            schema_version != ExecutionPlanSnapshot.SCHEMA_VERSION
            or actual_schema_version != schema_version
        ):
            issues.append(
                SnapshotVerificationIssue(
                    "schema_version_unsupported",
                    f"Unsupported SchemaVersion: {actual_schema_version}",
                )
            )

        if canonical_hash(graph_payload) != snapshot.graph_hash:
            issues.append(
                SnapshotVerificationIssue(
                    "graph_hash_mismatch",
                    "GraphHash does not match the supplied graph.",
                )
            )

        if (
            canonical_hash(validation_projection(validation_report))
            != snapshot.validation_hash
        ):
            issues.append(
                SnapshotVerificationIssue(
                    "validation_hash_mismatch",
                    "ValidationHash does not match the validation record.",
                )
            )

        missing = [
            key
            for key in PLANNER_METADATA_KEYS
            if not snapshot.planner_metadata.get(key)
        ]
        if missing:
            issues.append(
                SnapshotVerificationIssue(
                    "planner_metadata_missing",
                    "PlannerMetadata is missing: " + ", ".join(missing),
                )
            )

        if not 0.0 <= snapshot.planning_confidence <= 1.0:
            issues.append(
                SnapshotVerificationIssue(
                    "planning_confidence_invalid",
                    "PlanningConfidence must be between 0 and 1.",
                )
            )

        return SnapshotVerificationResult(
            is_valid=not issues,
            issues=tuple(issues),
        )

    def verify_or_raise(self, snapshot, graph, validation_report, **kwargs):
        result = self.verify(
            snapshot,
            graph,
            validation_report,
            **kwargs,
        )
        if not result.is_valid:
            codes = ", ".join(issue.code for issue in result.issues)
            raise ValueError(
                "ExecutionPlanSnapshot verification failed: " + codes
            )
        return result


def validation_projection(report):
    def issue(item):
        return {
            "code": item.code,
            "severity": item.severity.value,
            "nodeId": item.node_id,
            "edgeId": item.edge_id,
            "fieldPath": item.field_path,
            "suggestedFix": item.suggested_fix,
        }

    return {
        "graphId": report.graph_id,
        "isValid": report.is_valid,
        "errors": [issue(item) for item in report.errors],
        "warnings": [issue(item) for item in report.warnings],
    }


def canonical_hash(value):
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
