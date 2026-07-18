from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExecutionStep:
    """One planned runtime tool step."""

    index: int
    tool_name: str
    action: str = ""
    input_data: dict = field(default_factory=dict)
    raw_text: str = ""
    depends_on: tuple[int, ...] = ()

    def to_dict(self):
        """Return a diagnostics-friendly dictionary."""
        return {
            "index": self.index,
            "tool_name": self.tool_name,
            "action": self.action,
            "input_data": dict(self.input_data),
            "raw_text": self.raw_text,
            "depends_on": list(self.depends_on),
        }
