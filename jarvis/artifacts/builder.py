"""The only component authorized to create new ArtifactRef values."""

from hashlib import sha256
import json
from uuid import NAMESPACE_URL, uuid5

from .models import (
    CURRENT_ARTIFACT_SCHEMA_VERSION,
    ArtifactBuildRequest,
    ArtifactProvenance,
    ArtifactRef,
    ArtifactStatus,
    utc_now,
)


class ArtifactBuilder:
    def build(self, request: ArtifactBuildRequest):
        if not request.source_execution_id or not request.node_id or not request.output_key:
            raise ValueError("Execution, node, and output identities are required.")
        checksum = request.checksum or stable_checksum(
            {
                "externalResourceId": request.external_resource_id,
                "uri": request.uri,
                "type": request.artifact_type.value,
            }
        )
        resource_identity = request.external_resource_id or checksum
        identity = ":".join(
            (
                request.source_execution_id,
                request.node_id,
                request.output_key,
                resource_identity,
            )
        )
        artifact_id = str(uuid5(NAMESPACE_URL, f"jarvis:artifact:{identity}"))
        now = utc_now()
        provider = str(request.provider or "")
        return ArtifactRef(
            artifact_id=artifact_id,
            artifact_type=request.artifact_type,
            provider=provider,
            title=request.title,
            summary=request.summary,
            created_at=now,
            updated_at=now,
            owner=request.owner,
            tags=tuple(sorted(set(request.tags))),
            status=ArtifactStatus.CREATED,
            source_goal_id=request.source_goal_id,
            source_execution_id=request.source_execution_id,
            parent_artifact_id=request.parent_artifact_id,
            child_artifact_ids=(),
            external_resource_id=request.external_resource_id,
            checksum=checksum,
            retention_class=request.retention_class,
            visibility=request.visibility,
            schema_version=CURRENT_ARTIFACT_SCHEMA_VERSION,
            produced_by_capability=request.produced_by_capability,
            produced_by_provider=provider,
            produced_by_ability_version=request.ability_version,
            provenance=ArtifactProvenance(
                created_by="ArtifactBuilder",
                provider=provider,
                execution_id=request.source_execution_id,
                node_id=request.node_id,
                derived_from=request.derived_from,
            ),
            uri=request.uri,
            metadata=request.metadata,
        )


def stable_checksum(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()
