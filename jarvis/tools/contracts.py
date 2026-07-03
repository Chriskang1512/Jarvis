from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolMetadata:
    """Describe one callable Jarvis tool."""

    name: str
    description: str
    safe: bool = True


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
