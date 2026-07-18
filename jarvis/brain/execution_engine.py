from dataclasses import dataclass, field
from time import perf_counter


EXECUTION_STATUS_CREATED = "CREATED"
EXECUTION_STATUS_RUNNING = "RUNNING"
EXECUTION_STATUS_COMPLETED = "COMPLETED"
EXECUTION_STATUS_FAILED = "FAILED"
EXECUTION_STATUS_CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class RetryPolicy:
    """Decide whether a failed step should be retried."""

    max_retries: int = 0

    def should_retry(self, retry_count):
        """Return whether another attempt is allowed."""
        return retry_count < self.max_retries


@dataclass(frozen=True)
class ExecutionMetrics:
    """Runtime execution metrics for diagnostics."""

    execution_time: float = 0.0
    router_time: float = 0.0
    dispatcher_time: float = 0.0
    retry_count: int = 0
    fallback_used: bool = False

    def to_dict(self):
        """Return a stable diagnostics payload."""
        return {
            "execution_time": self.execution_time,
            "router_time": self.router_time,
            "dispatcher_time": self.dispatcher_time,
            "retry_count": self.retry_count,
            "fallback_used": self.fallback_used,
        }


@dataclass(frozen=True)
class ExecutionContext:
    """Plan execution context used after planning."""

    plan: object
    step: object = None
    retry_count: int = 0
    start_time: float = 0.0
    deadline: object = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        """Set a monotonic start time when omitted."""
        if self.start_time == 0.0:
            object.__setattr__(self, "start_time", perf_counter())

    def to_dict(self):
        """Return a stable diagnostics payload."""
        return {
            "plan": plan_to_dict(self.plan),
            "step": step_to_dict(self.step),
            "retry_count": self.retry_count,
            "start_time": self.start_time,
            "deadline": self.deadline,
            "metadata": dict(self.metadata),
        }


def create_metrics(
    started,
    router_time=0.0,
    dispatcher_time=0.0,
    retry_count=0,
    fallback_used=False,
):
    """Create execution metrics from accumulated timings."""
    return ExecutionMetrics(
        execution_time=perf_counter() - started,
        router_time=router_time,
        dispatcher_time=dispatcher_time,
        retry_count=retry_count,
        fallback_used=fallback_used,
    )


def execute_parallel(plan):
    """Reserved parallel execution interface for a future sprint."""
    raise NotImplementedError("Parallel plan execution is not implemented yet.")


def plan_to_dict(plan):
    """Return a serializable plan payload without importing runtime helpers."""
    if plan is None:
        return None

    if hasattr(plan, "to_dict"):
        return plan.to_dict()

    return plan


def step_to_dict(step):
    """Return a serializable plan step payload."""
    if step is None:
        return None

    if hasattr(step, "to_dict"):
        return step.to_dict()

    return step
