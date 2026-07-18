from dataclasses import dataclass, field


@dataclass(frozen=True)
class DispatchContext:
    """Context for one dispatcher selection or execution."""

    text: str = ""
    source: str = "runtime"
    session_id: str = ""
    metadata: dict = field(default_factory=dict)
