from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4


PLAN_STATUS_CREATED = "CREATED"
PLAN_STATUS_EMPTY = "EMPTY"
STEP_STATUS_PENDING = "PENDING"
STEP_STATUS_RUNNING = "RUNNING"
STEP_STATUS_COMPLETED = "COMPLETED"
STEP_STATUS_FAILED = "FAILED"


@dataclass(frozen=True)
class PlanStep:
    """One executable step in a runtime plan."""

    tool: str
    parameters: dict = field(default_factory=dict)
    depends_on: tuple = ()
    status: str = STEP_STATUS_PENDING
    timeout_ms: int = 0

    def to_dict(self):
        """Return a stable diagnostics payload."""
        return {
            "tool": self.tool,
            "parameters": dict(self.parameters),
            "depends_on": list(self.depends_on),
            "status": self.status,
            "timeout_ms": self.timeout_ms,
        }


@dataclass(frozen=True)
class Plan:
    """A lightweight runtime plan created from one intent."""

    goal: str
    id: str = ""
    steps: tuple = ()
    status: str = PLAN_STATUS_CREATED
    created_at: str = ""

    def __post_init__(self):
        """Normalize mutable inputs into immutable replay-safe values."""
        object.__setattr__(self, "steps", tuple(self.steps))

        if self.id == "":
            object.__setattr__(self, "id", create_plan_id())

        if self.created_at == "":
            object.__setattr__(self, "created_at", datetime.now().isoformat(timespec="seconds"))

    def to_dict(self):
        """Return a stable diagnostics payload."""
        return {
            "id": self.id,
            "goal": self.goal,
            "steps": [step.to_dict() for step in self.steps],
            "status": self.status,
            "created_at": self.created_at,
        }


class Planner:
    """Rule-based v0.5 planner foundation."""

    def plan(self, intent):
        """Return a single-step plan for the current intent."""
        if intent is None:
            return Plan(goal="", steps=(), status=PLAN_STATUS_EMPTY)

        return Plan(
            goal=intent.name,
            steps=(
                PlanStep(
                    tool=intent.name,
                    parameters=dict(intent.parameters),
                    depends_on=(),
                    status=STEP_STATUS_PENDING,
                    timeout_ms=0,
                ),
            ),
            status=PLAN_STATUS_CREATED,
        )


def create_plan_id():
    """Create a short plan ID for diagnostics and replay."""
    return f"P-{uuid4().hex[:4].upper()}"


def update_plan_step_status(plan, step_index, status):
    """Return a new plan with one updated step status."""
    steps = list(plan.steps)
    step = steps[step_index]
    steps[step_index] = PlanStep(
        tool=step.tool,
        parameters=dict(step.parameters),
        depends_on=tuple(step.depends_on),
        status=status,
        timeout_ms=step.timeout_ms,
    )
    return Plan(
        id=plan.id,
        goal=plan.goal,
        steps=tuple(steps),
        status=plan.status,
        created_at=plan.created_at,
    )
