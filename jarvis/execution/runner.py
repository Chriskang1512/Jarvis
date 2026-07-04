from datetime import datetime
from time import perf_counter
from uuid import uuid4

from jarvis.execution.context import ExecutionContext
from jarvis.execution.contracts import ExecutionNodeResult, ExecutionRunResult
from jarvis.execution.node_state import NodeStatus, result_status
from jarvis.result_merge import DefaultResultMerger


class ExecutionGraphRunner:
    """Walk a validated execution graph sequentially."""

    def __init__(self, capability_router, dispatcher, diagnostics_collector=None, result_merger=None):
        """Create a runner with injected routing and execution interfaces."""
        self.capability_router = capability_router
        self.dispatcher = dispatcher
        self.diagnostics_collector = diagnostics_collector
        self.result_merger = result_merger or DefaultResultMerger()

    def run_unified(self, plan):
        """Execute a graph and return a merged unified response."""
        execution_result = self.run(plan)
        return self.result_merger.merge(
            execution_result.results,
            metadata=self.build_merge_metadata(execution_result),
        )

    def run(self, plan):
        """Execute graph nodes in order and return ordered node results."""
        plan_dict = as_plan_dict(plan)
        graph = plan_dict.get("graph", {})
        nodes = list(graph.get("nodes", []))
        plan_id = plan_dict.get("plan_id", "")
        execution_id = create_execution_id()
        context = ExecutionContext(execution_id=execution_id)
        self.log_event(f"[PLAN] {plan_id}")
        started = perf_counter()
        results = []

        try:
            for node in nodes:
                results.append(self.run_node(node, context))
        finally:
            context.destroy()
            self.log_event("Execution Context destroyed")

        completed_count = len([result for result in results if result.status == result_status(NodeStatus.COMPLETED)])
        failed_count = len([result for result in results if result.status == result_status(NodeStatus.FAILED)])
        run_status = "completed" if failed_count == 0 else "failed"
        duration_ms = int((perf_counter() - started) * 1000)
        self.log_event("Execution Summary")
        self.log_event(f"Nodes: {len(results)}")
        self.log_event(f"Completed: {completed_count}")
        self.log_event(f"Failed: {failed_count}")
        self.log_event(f"Duration: {duration_ms} ms")

        return ExecutionRunResult(
            execution_id=execution_id,
            plan_id=plan_id,
            status=run_status,
            results=results,
        )

    def build_merge_metadata(self, execution_result):
        """Build run metadata for ResultMerger without embedding unified output."""
        completed_count = len(
            [result for result in execution_result.results if result.status == result_status(NodeStatus.COMPLETED)]
        )
        failed_count = len(
            [result for result in execution_result.results if result.status == result_status(NodeStatus.FAILED)]
        )
        return {
            "execution_id": execution_result.execution_id,
            "plan_id": execution_result.plan_id,
            "status": execution_result.status,
            "node_count": len(execution_result.results),
            "completed_nodes": completed_count,
            "failed_nodes": failed_count,
        }

    def run_node(self, node, context):
        """Execute one graph node through router and dispatcher."""
        node_id = node.get("id", "")
        capability = node.get("capability", "")
        started_at = timestamp()
        started = perf_counter()
        self.log_event(f"[RUNNER] {node_id} {NodeStatus.RUNNING.value}")

        try:
            request = self.capability_router.route(node, context=context)
            tool_result = self.dispatcher.execute(request)
        except Exception as error:
            return self.create_failed_result(node_id, capability, str(error), started_at, started)

        finished_at = timestamp()
        duration_ms = int((perf_counter() - started) * 1000)

        if not getattr(tool_result, "success", False):
            self.log_event(f"[RUNNER] {node_id} {NodeStatus.FAILED.value} ({duration_ms} ms)")
            return ExecutionNodeResult(
                node_id=node_id,
                status=result_status(NodeStatus.FAILED),
                result={
                    "error": getattr(tool_result, "error", "Tool execution failed."),
                },
                started_at=started_at,
                finished_at=finished_at,
                capability=capability,
            )

        output = getattr(tool_result, "output", None)
        context.store_result(node_id=node_id, result=output)
        self.log_event(f"[RUNNER] {node_id} {NodeStatus.COMPLETED.value} ({duration_ms} ms)")
        self.log_event("Context updated")
        return ExecutionNodeResult(
            node_id=node_id,
            status=result_status(NodeStatus.COMPLETED),
            result=output,
            started_at=started_at,
            finished_at=finished_at,
            capability=capability,
        )

    def create_failed_result(self, node_id, capability, error, started_at, started):
        """Return a failed node result."""
        finished_at = timestamp()
        duration_ms = int((perf_counter() - started) * 1000)
        self.log_event(f"[RUNNER] {node_id} {NodeStatus.FAILED.value} ({duration_ms} ms)")
        return ExecutionNodeResult(
            node_id=node_id,
            status=result_status(NodeStatus.FAILED),
            result={"error": error},
            started_at=started_at,
            finished_at=finished_at,
            capability=capability,
        )

    def log_event(self, message):
        """Publish execution diagnostics when available."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.log_event(message)


def as_plan_dict(plan):
    """Return a plan dictionary from contract or raw dictionary input."""
    if hasattr(plan, "to_dict"):
        return plan.to_dict()

    return plan


def timestamp():
    """Return an ISO timestamp for execution result contracts."""
    return datetime.now().isoformat(timespec="milliseconds")


def create_execution_id():
    """Create a diagnostic-friendly execution ID."""
    return f"exec_{uuid4().hex[:12]}"
