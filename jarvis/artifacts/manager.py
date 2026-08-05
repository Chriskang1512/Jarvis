"""Artifact capture boundary for verified Native TaskGraph outputs."""

from .builder import ArtifactBuilder, stable_checksum
from .models import ArtifactBuildRequest, ArtifactType
from .search import ArtifactIndexer, ArtifactSearch


class ArtifactManager:
    def __init__(self, repository, *, builder=None, semantic_provider=None):
        self.repository = repository
        self.builder = builder or ArtifactBuilder()
        self.indexer = ArtifactIndexer(repository)
        self.search = ArtifactSearch(repository, semantic_provider)

    def capture_execution(self, graph, session):
        artifacts = []
        for node in graph.nodes:
            for output_key, definition in node.outputs.items():
                if not definition.artifact_type or not session.output_store.has(node.node_id, output_key):
                    continue
                value = session.output_store.get(node.node_id, output_key).value
                artifact = self.builder.build(
                    ArtifactBuildRequest(
                        artifact_type=normalize_type(definition.artifact_type),
                        title=f"{node.display_name or node.capability_id}: {output_key}",
                        summary=f"Verified {definition.value_type} output",
                        source_goal_id=graph.goal_id,
                        source_execution_id=session.session_id,
                        node_id=node.node_id,
                        output_key=output_key,
                        produced_by_capability=node.capability_id,
                        provider=str(node.metadata.get("provider", "")),
                        ability_version=str(node.metadata.get("abilityVersion", "")),
                        external_resource_id=extract_external_id(value),
                        uri=extract_uri(value),
                        checksum=stable_checksum(value),
                        tags=(node.capability_id.split(".", 1)[0], definition.artifact_type),
                        metadata={"outputKey": output_key, "valueType": definition.value_type},
                    )
                )
                artifact, _ = self.indexer.index(artifact)
                artifacts.append(artifact)
        return tuple(artifacts)


def normalize_type(value):
    normalized = str(value).replace("_", "").replace("-", "").casefold()
    aliases = {
        "calendareventref": ArtifactType.CALENDAR_EVENT,
        "emailmessageref": ArtifactType.MAIL,
        "mailref": ArtifactType.MAIL,
        "fileref": ArtifactType.FILE,
        "documentref": ArtifactType.DOCUMENT,
        "imageref": ArtifactType.IMAGE,
        "audioref": ArtifactType.AUDIO,
        "videoref": ArtifactType.VIDEO,
    }
    if normalized in aliases:
        return aliases[normalized]
    for item in ArtifactType:
        if item.value.replace("_", "").casefold() == normalized or item.name.replace("_", "").casefold() == normalized:
            return item
    return ArtifactType.CUSTOM


def extract_external_id(value):
    if not isinstance(value, dict):
        return ""
    for key in ("id", "eventId", "messageId", "fileId", "resourceId"):
        if value.get(key):
            return str(value[key])
    return ""


def extract_uri(value):
    if not isinstance(value, dict):
        return ""
    for key in ("uri", "url", "path"):
        if value.get(key):
            return str(value[key])
    return ""
