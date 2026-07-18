from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlanStepResult:
    """Execution result for one planned step."""

    step_index: int
    tool_name: str
    success: bool
    response: str = ""
    tool_result: object = None
    error: str = ""
    failure_reason: str = ""
    validator: str = ""
    field: str = ""


@dataclass(frozen=True)
class PlanResult:
    """Merged result of an ExecutionPlan run."""

    success: bool
    plan: object = None
    step_results: list[PlanStepResult] = field(default_factory=list)
    response: str = ""
    error: str = ""
    task: object = None

    def to_natural_language(self):
        """Return the merged spoken response."""
        if self.response:
            return self.response

        if not self.success:
            return self.error

        return "\n".join(result.response for result in self.step_results if result.response)
