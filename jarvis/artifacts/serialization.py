"""Versioned ArtifactRef JSON serialization."""

from .models import (
    ArtifactProvenance,
    ArtifactRef,
    ArtifactRetentionClass,
    ArtifactStatus,
    ArtifactType,
    ArtifactVisibility,
)


def artifact_to_dict(value):
    return {
        "schemaVersion": value.schema_version,
        "artifactId": value.artifact_id,
        "artifactType": value.artifact_type.value,
        "provider": value.provider,
        "title": value.title,
        "summary": value.summary,
        "createdAt": value.created_at.isoformat(),
        "updatedAt": value.updated_at.isoformat(),
        "owner": value.owner,
        "tags": list(value.tags),
        "status": value.status.value,
        "sourceGoalId": value.source_goal_id,
        "sourceExecutionId": value.source_execution_id,
        "parentArtifactId": value.parent_artifact_id,
        "childArtifactIds": list(value.child_artifact_ids),
        "externalResourceId": value.external_resource_id,
        "checksum": value.checksum,
        "retentionClass": value.retention_class.value,
        "visibility": value.visibility.value,
        "producedByCapability": value.produced_by_capability,
        "producedByProvider": value.produced_by_provider,
        "producedByAbilityVersion": value.produced_by_ability_version,
        "provenance": {
            "createdBy": value.provenance.created_by,
            "provider": value.provenance.provider,
            "executionId": value.provenance.execution_id,
            "nodeId": value.provenance.node_id,
            "timestamp": value.provenance.timestamp.isoformat(),
            "derivedFrom": list(value.provenance.derived_from),
        },
        "uri": value.uri,
        "metadata": dict(value.metadata),
    }


def artifact_from_dict(value):
    from datetime import datetime

    provenance = value.get("provenance", {})
    return ArtifactRef(
        artifact_id=str(value["artifactId"]),
        artifact_type=ArtifactType(value.get("artifactType", "Custom")),
        provider=str(value.get("provider", "")),
        title=str(value.get("title", "")),
        summary=str(value.get("summary", "")),
        created_at=datetime.fromisoformat(value["createdAt"]),
        updated_at=datetime.fromisoformat(value["updatedAt"]),
        owner=str(value.get("owner", "")),
        tags=tuple(value.get("tags", ())),
        status=ArtifactStatus(value.get("status", "Created")),
        source_goal_id=str(value.get("sourceGoalId", "")),
        source_execution_id=str(value.get("sourceExecutionId", "")),
        parent_artifact_id=str(value.get("parentArtifactId", "")),
        child_artifact_ids=tuple(value.get("childArtifactIds", ())),
        external_resource_id=str(value.get("externalResourceId", "")),
        checksum=str(value.get("checksum", "")),
        retention_class=ArtifactRetentionClass(
            value.get("retentionClass", "Standard")
        ),
        visibility=ArtifactVisibility(value.get("visibility", "Private")),
        schema_version=int(value.get("schemaVersion", 1)),
        produced_by_capability=str(value.get("producedByCapability", "")),
        produced_by_provider=str(value.get("producedByProvider", "")),
        produced_by_ability_version=str(value.get("producedByAbilityVersion", "")),
        provenance=ArtifactProvenance(
            created_by=str(provenance.get("createdBy", "")),
            provider=str(provenance.get("provider", "")),
            execution_id=str(provenance.get("executionId", "")),
            node_id=str(provenance.get("nodeId", "")),
            timestamp=datetime.fromisoformat(provenance["timestamp"]),
            derived_from=tuple(provenance.get("derivedFrom", ())),
        ),
        uri=str(value.get("uri", "")),
        metadata=dict(value.get("metadata", {})),
    )


class ArtifactSerializer:
    """Versioned serializer used by repositories, replay, and SDK surfaces."""

    def serialize(self, artifact):
        return artifact_to_dict(artifact)

    def restore(self, payload):
        return artifact_from_dict(payload)
