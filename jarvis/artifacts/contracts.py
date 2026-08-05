"""Provider boundary: Providers describe outputs; ArtifactBuilder creates refs."""

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .models import ArtifactType


@dataclass(frozen=True)
class ProviderArtifactResult:
    artifact_type: ArtifactType
    value: Any
    provider: str
    external_resource_id: str = ""
    uri: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ArtifactProducingProvider(Protocol):
    """A Provider returns a description, never an ArtifactRef instance."""

    def execute(self, operation, inputs) -> ProviderArtifactResult: ...
