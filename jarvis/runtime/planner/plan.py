from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from jarvis.runtime.planner.step import ExecutionStep


@dataclass(frozen=True)
class ExecutionPlan:
    """A runtime plan that describes ordered tool execution."""

    raw_text: str
    steps: tuple[ExecutionStep, ...] = ()
    unsupported_reason: str = ""
    requires_clarification: bool = False
    clarification_question: str = ""
    intent_error: str = ""
    id: str = ""
    created_at: str = ""

    def __post_init__(self):
        """Fill replay-friendly defaults."""
        object.__setattr__(self, "steps", tuple(self.steps))

        if self.id == "":
            object.__setattr__(self, "id", f"RP-{uuid4().hex[:6].upper()}")

        if self.created_at == "":
            object.__setattr__(self, "created_at", datetime.now().isoformat(timespec="seconds"))

    @property
    def step_count(self):
        """Return number of planned steps."""
        return len(self.steps)

    @property
    def multi_tool(self):
        """Return whether this plan has more than one step."""
        return len(self.steps) > 1

    def to_dict(self):
        """Return a diagnostics-friendly dictionary."""
        return {
            "id": self.id,
            "raw_text": self.raw_text,
            "step_count": len(self.steps),
            "multi_tool": self.multi_tool,
            "unsupported_reason": self.unsupported_reason,
            "requires_clarification": self.requires_clarification,
            "clarification_question": self.clarification_question,
            "intent_error": self.intent_error,
            "created_at": self.created_at,
            "steps": [step.to_dict() for step in self.steps],
        }


def create_execution_plan(raw_text, steps=None):
    """Create an ExecutionPlan from mutable step data."""
    return ExecutionPlan(raw_text=str(raw_text or ""), steps=tuple(steps or ()))
