from dataclasses import dataclass, field
from enum import Enum

from jarvis.permissions import PermissionLevel


class AbilityType(str, Enum):
    """Classify abilities by execution boundary."""

    NATIVE = "native"
    INTEGRATION = "integration"


@dataclass(frozen=True)
class AbilityMetadata:
    """Describe one Jarvis ability manifest."""

    id: str
    name: str
    type: AbilityType
    permission: PermissionLevel
    description: str
    input_schema: dict
    output_schema: dict
    version: str = "0.1.0"
    author: str = "Jarvis"
    capabilities: list[str] = field(default_factory=list)
    provider: str = ""
    priority: str = "normal"
    aliases: list[str] = field(default_factory=list)
    supported_intents: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    input_prefixes: list[str] = field(default_factory=list)
    route_confidence: float = 0.75
