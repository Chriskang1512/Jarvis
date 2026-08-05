"""Serialization for Dashboard projection repositories and APIs."""

from datetime import datetime

from jarvis.runtime.state import RuntimeState
from .projection_models import NodeView, ProjectionVersion, RuntimeSessionView, TimelineView


def session_to_dict(value):
    return {
        "sessionId": value.session_id,
        "goal": value.goal,
        "status": value.status,
        "startedAt": value.started_at.isoformat(),
        "completedAt": value.completed_at.isoformat() if value.completed_at else None,
        "elapsed": value.elapsed_seconds,
        "plannerStatus": value.planner_status,
        "executionStatus": value.execution_status,
        "verificationStatus": value.verification_status,
        "memoryStatus": value.memory_status,
        "artifactStatus": value.artifact_status,
        "retryCount": value.retry_count,
        "waitingPermission": value.waiting_permission,
        "currentNode": value.current_node,
        "currentRuntimeState": value.current_runtime_state.value,
        "nodes": {key: node_to_dict(item) for key, item in value.nodes.items()},
        "timeline": [timeline_to_dict(item) for item in value.timeline],
        "lastEventSequence": value.last_event_sequence,
        "projectionVersion": version_to_dict(value.projection_version),
    }


def node_to_dict(value):
    return {
        "nodeId": value.node_id,
        "nodeType": value.node_type,
        "status": value.status,
        "startedAt": value.started_at.isoformat() if value.started_at else None,
        "finishedAt": value.finished_at.isoformat() if value.finished_at else None,
        "elapsed": value.elapsed_seconds,
        "retryCount": value.retry_count,
        "provider": value.provider,
        "ability": value.ability,
        "artifactIds": list(value.artifact_ids),
        "memoryIds": list(value.memory_ids),
    }


def timeline_to_dict(value):
    return {
        "eventSequence": value.event_sequence,
        "eventType": value.event_type,
        "occurredAt": value.occurred_at.isoformat(),
        "sessionId": value.session_id,
        "nodeId": value.node_id,
        "status": value.status,
        "details": dict(value.details),
    }


def version_to_dict(value):
    if value is None:
        return None
    return {
        "projectionId": value.projection_id,
        "schemaVersion": value.schema_version,
        "generatedAt": value.generated_at.isoformat(),
        "runtimeVersion": value.runtime_version,
    }


def session_from_dict(value):
    version = value.get("projectionVersion") or {}
    return RuntimeSessionView(
        session_id=value["sessionId"], goal=value.get("goal", ""),
        status=value.get("status", "Running"),
        started_at=datetime.fromisoformat(value["startedAt"]),
        completed_at=datetime.fromisoformat(value["completedAt"]) if value.get("completedAt") else None,
        planner_status=value.get("plannerStatus", "Pending"),
        execution_status=value.get("executionStatus", "Pending"),
        verification_status=value.get("verificationStatus", "Pending"),
        memory_status=value.get("memoryStatus", "Pending"),
        artifact_status=value.get("artifactStatus", "Pending"),
        retry_count=int(value.get("retryCount", 0)),
        waiting_permission=bool(value.get("waitingPermission", False)),
        current_node=value.get("currentNode", ""),
        current_runtime_state=RuntimeState(value.get("currentRuntimeState", "Idle")),
        nodes={key: node_from_dict(item) for key, item in value.get("nodes", {}).items()},
        timeline=tuple(timeline_from_dict(item) for item in value.get("timeline", ())),
        last_event_sequence=int(value.get("lastEventSequence", 0)),
        projection_version=ProjectionVersion(
            version.get("projectionId", "runtime-sessions"),
            int(version.get("schemaVersion", 1)),
            datetime.fromisoformat(version["generatedAt"]) if version.get("generatedAt") else datetime.now().astimezone(),
            version.get("runtimeVersion", "v1.5"),
        ),
    )


def node_from_dict(value):
    return NodeView(
        node_id=value["nodeId"], node_type=value.get("nodeType", ""),
        status=value.get("status", "Pending"),
        started_at=datetime.fromisoformat(value["startedAt"]) if value.get("startedAt") else None,
        finished_at=datetime.fromisoformat(value["finishedAt"]) if value.get("finishedAt") else None,
        retry_count=int(value.get("retryCount", 0)), provider=value.get("provider", ""),
        ability=value.get("ability", ""), artifact_ids=tuple(value.get("artifactIds", ())),
        memory_ids=tuple(value.get("memoryIds", ())),
    )


def timeline_from_dict(value):
    return TimelineView(
        int(value["eventSequence"]), value["eventType"],
        datetime.fromisoformat(value["occurredAt"]), value["sessionId"],
        value.get("nodeId", ""), value.get("status", ""), value.get("details", {}),
    )
