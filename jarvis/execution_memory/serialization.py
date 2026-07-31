"""Forward-compatible JSON projection for execution memories."""

from __future__ import annotations

from datetime import datetime

from .models import (
    ExecutionMemoryRecord,
    HistoryEntry,
    HistoryType,
    MemoryConfidence,
    MemoryFactType,
    MemoryProvenance,
    MemoryRetentionPolicy,
    RetentionClass,
    SessionReplayReference,
)


def record_to_dict(record):
    return {
        "schemaVersion": record.schema_version,
        "summaryVersion": record.summary_version,
        "recordId": record.record_id,
        "sourceExecutionId": record.source_execution_id,
        "goalId": record.goal_id,
        "sessionId": record.session_id,
        "snapshotId": record.snapshot_id,
        "graphId": record.graph_id,
        "goalSignature": record.goal_signature,
        "outcome": record.outcome,
        "resultHash": record.result_hash,
        "histories": [
            {
                "historyType": item.history_type.value,
                "status": item.status,
                "nodeId": item.node_id,
                "capabilityId": item.capability_id,
                "occurredAt": item.occurred_at.isoformat(),
                "metadata": dict(item.metadata),
            }
            for item in record.histories
        ],
        "replayReference": {
            "sessionId": record.replay_reference.session_id,
            "eventRange": list(record.replay_reference.event_range),
            "journalReference": record.replay_reference.journal_reference,
            "available": record.replay_reference.available,
            "retentionClass": record.replay_reference.retention_class.value,
        },
        "provenance": {
            "sourceType": record.provenance.source_type.value,
            "sourceExecutionId": record.provenance.source_execution_id,
            "sourceNodeId": record.provenance.source_node_id,
            "sourceProvider": record.provenance.source_provider,
            "generatedAt": record.provenance.generated_at.isoformat(),
            "derivedFrom": list(record.provenance.derived_from),
        },
        "confidence": {
            "factualConfidence": record.confidence.factual_confidence,
            "retrievalConfidence": record.confidence.retrieval_confidence,
            "verificationStatus": record.confidence.verification_status,
        },
        "retentionClass": record.retention_class.value,
        "retentionPolicy": {
            "retentionClass": record.retention_policy.retention_class.value,
            "expiresAt": (
                record.retention_policy.expires_at.isoformat()
                if record.retention_policy.expires_at
                else None
            ),
            "archiveAfterDays": (
                record.retention_policy.archive_after_days
            ),
            "allowAutomaticDeletion": (
                record.retention_policy.allow_automatic_deletion
            ),
        },
        "tags": list(record.tags),
        "redactedMetadata": dict(record.redacted_metadata),
        "createdAt": record.created_at.isoformat(),
    }


def record_from_dict(value):
    replay = value["replayReference"]
    provenance = value["provenance"]
    confidence = value["confidence"]
    retention_policy = value.get("retentionPolicy", {})
    return ExecutionMemoryRecord(
        schema_version=int(value["schemaVersion"]),
        summary_version=int(value.get("summaryVersion", 1)),
        record_id=str(value["recordId"]),
        source_execution_id=str(value["sourceExecutionId"]),
        goal_id=str(value["goalId"]),
        session_id=str(value["sessionId"]),
        snapshot_id=str(value["snapshotId"]),
        graph_id=str(value["graphId"]),
        goal_signature=str(value.get("goalSignature", "")),
        outcome=str(value["outcome"]),
        result_hash=str(value["resultHash"]),
        histories=tuple(
            HistoryEntry(
                HistoryType(item["historyType"]),
                str(item["status"]),
                str(item.get("nodeId", "")),
                str(item.get("capabilityId", "")),
                datetime.fromisoformat(item["occurredAt"]),
                item.get("metadata", {}),
            )
            for item in value.get("histories", ())
        ),
        replay_reference=SessionReplayReference(
            str(replay["sessionId"]),
            tuple(replay.get("eventRange", (0, 0))),
            str(replay.get("journalReference", "")),
            bool(replay.get("available", False)),
            RetentionClass(replay.get("retentionClass", "Standard")),
        ),
        provenance=MemoryProvenance(
            MemoryFactType(provenance["sourceType"]),
            str(provenance["sourceExecutionId"]),
            str(provenance.get("sourceNodeId", "")),
            str(provenance.get("sourceProvider", "")),
            datetime.fromisoformat(provenance["generatedAt"]),
            tuple(provenance.get("derivedFrom", ())),
        ),
        confidence=MemoryConfidence(
            float(confidence["factualConfidence"]),
            float(confidence.get("retrievalConfidence", 0.0)),
            str(confidence["verificationStatus"]),
        ),
        retention_class=RetentionClass(
            value.get("retentionClass", "Standard")
        ),
        retention_policy=MemoryRetentionPolicy(
            RetentionClass(
                retention_policy.get("retentionClass", "Standard")
            ),
            (
                datetime.fromisoformat(retention_policy["expiresAt"])
                if retention_policy.get("expiresAt")
                else None
            ),
            retention_policy.get("archiveAfterDays"),
            bool(
                retention_policy.get(
                    "allowAutomaticDeletion", False
                )
            ),
        ),
        tags=tuple(value.get("tags", ())),
        redacted_metadata=value.get("redactedMetadata", {}),
        created_at=datetime.fromisoformat(value["createdAt"]),
    )
