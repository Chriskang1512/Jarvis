from dataclasses import dataclass

from jarvis.permissions import PermissionLevel


@dataclass
class PluginMetadata:
    """Describe one Jarvis plugin package."""

    id: str
    name: str
    version: str
    domain: str
    description: str
    author: str = "Jarvis"
    enabled: bool = True
    permission_level: PermissionLevel = PermissionLevel.SAFE
