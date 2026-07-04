from dataclasses import dataclass
from typing import Protocol


@dataclass
class ExecutionInputData:
    """Stable input contract sent to capability tools."""

    user_input: str
    previous_results: list
    execution_snapshot: object

    def to_dict(self):
        """Return the tool input dictionary."""
        return {
            "text": self.user_input,
            "user_input": self.user_input,
            "previous_results": list(self.previous_results),
            "execution_snapshot": self.execution_snapshot,
        }


@dataclass
class ExecutionNodeResult:
    """Execution result for one graph node."""

    node_id: str
    status: str
    result: object
    started_at: str
    finished_at: str
    capability: str = ""

    def to_dict(self):
        """Return a stable dictionary contract."""
        return {
            "node_id": self.node_id,
            "capability": self.capability,
            "status": self.status,
            "result": self.result,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass
class ExecutionRunResult:
    """Execution result for one validated plan."""

    execution_id: str
    plan_id: str
    status: str
    results: list[ExecutionNodeResult]

    def to_dict(self):
        """Return a stable dictionary contract."""
        return {
            "execution_id": self.execution_id,
            "plan_id": self.plan_id,
            "status": self.status,
            "results": [result.to_dict() for result in self.results],
        }


class CapabilityRouter(Protocol):
    """Protocol for routing capability intent nodes to executable requests."""

    def route(self, node):
        """Return an execution request for one node."""
        ...


class Dispatcher(Protocol):
    """Protocol for executing routed requests."""

    def execute(self, request):
        """Execute one routed request."""
        ...
