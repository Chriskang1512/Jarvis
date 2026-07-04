from dataclasses import dataclass, field

from jarvis.permissions import PermissionLevel


@dataclass
class CapabilityMetadata:
    """Describe one Jarvis capability plugin."""

    id: str
    name: str
    description: str
    version: str = "0.1.0"
    status: str = "alpha"
    owner: str = "Jarvis Team"
    enabled: bool = True
    permission_level: PermissionLevel = PermissionLevel.SAFE
    tools: list[str] = field(default_factory=list)
