from dataclasses import dataclass, field


@dataclass(frozen=True)
class DispatchSelection:
    """One selected tool candidate."""

    tool_name: str
    confidence: float
    input_data: dict = field(default_factory=dict)
    provider: str = ""
    priority: str = "normal"
    capability: str = ""


@dataclass(frozen=True)
class DispatchResult:
    """Result produced by RuntimeToolDispatcher."""

    success: bool
    selected: DispatchSelection | None = None
    tool_result: object = None
    response: object = ""
    error: str = ""
    duration_ms: int = 0
    multi_tool_ready: bool = False
    selections: list[DispatchSelection] = field(default_factory=list)
