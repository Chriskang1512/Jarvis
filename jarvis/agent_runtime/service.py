from typing import Protocol, runtime_checkable

from jarvis.agent_runtime.exceptions import AgentRuntimeStopped
from jarvis.agent_runtime.models import AgentRuntimeState, AgentTickResult
from jarvis.scheduler.clock import SystemClock


@runtime_checkable
class ExecutionKernel(Protocol):
    """Stable execution interface used by Scheduler and AgentRuntime.

    Kernel implementations execute plans and return UnifiedResult.
    """

    def run_unified(self, plan):
        """Run one scheduled payload and return a UnifiedResult."""
        ...


class AgentRuntime:
    """Coordinate Scheduler and Execution Kernel lifecycle with manual ticks."""

    def __init__(self, scheduler, execution_kernel, clock=None):
        """Create a runtime with injected scheduler, kernel, and clock."""
        self.scheduler = scheduler
        self.execution_kernel = execution_kernel
        self.clock = clock or SystemClock()
        self.state = AgentRuntimeState.STOPPED

    def start(self):
        """Start the runtime lifecycle without starting a background loop."""
        self.state = AgentRuntimeState.IDLE
        return self.state

    def stop(self):
        """Stop the runtime lifecycle."""
        self.state = AgentRuntimeState.STOPPED
        return self.state

    def tick(self, now=None):
        """Run one manual scheduler check and trigger due work."""
        if self.state == AgentRuntimeState.STOPPED:
            raise AgentRuntimeStopped("AgentRuntime must be started before tick().")

        checked_at = now or self.clock.now()
        self.state = AgentRuntimeState.CHECKING
        due_count = len(self.scheduler.due_tasks(checked_at))

        if due_count == 0:
            self.state = AgentRuntimeState.IDLE
            return AgentTickResult(
                runtime_state=self.state,
                checked_at=checked_at,
                due_count=0,
                trigger_results=(),
            )

        self.state = AgentRuntimeState.RUNNING

        try:
            trigger_results = tuple(
                self.scheduler.trigger_due(
                    checked_at,
                    execution_runner=self.execution_kernel,
                )
            )
        except Exception as error:
            self.state = AgentRuntimeState.FAILED
            return AgentTickResult(
                runtime_state=self.state,
                checked_at=checked_at,
                due_count=due_count,
                trigger_results=(),
                error=str(error),
            )

        self.state = AgentRuntimeState.IDLE
        return AgentTickResult(
            runtime_state=self.state,
            checked_at=checked_at,
            due_count=due_count,
            trigger_results=trigger_results,
        )
