from dataclasses import dataclass, field
from typing import Protocol

from jarvis.permissions import PermissionLevel


@dataclass
class ToolMetadata:
    """Describe one callable Jarvis tool."""

    name: str
    description: str
    version: str = "0.1.0"
    domain: str = "core"
    permission_level: PermissionLevel = PermissionLevel.SAFE
    safety_level: PermissionLevel = PermissionLevel.SAFE
    safe: bool = True
    deprecated: bool = False
    priority: int = 0
    capability: str = ""
    aliases: list[str] = field(default_factory=list)
    supported_intents: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    input_mode: str = "text"
    input_prefixes: list[str] = field(default_factory=list)
    allow_empty_input: bool = False
    route_confidence: float = 0.75


@dataclass
class ToolRequest:
    """Represent a tool execution request."""

    tool_name: str
    input_data: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    """Represent a structured tool execution result."""

    tool_name: str
    success: bool
    output: object = None
    error: str = ""


class Tool(Protocol):
    """Common contract for every Jarvis tool."""

    metadata: ToolMetadata

    def execute(self, input_data):
        """Execute the tool and return a ToolResult."""
        ...
