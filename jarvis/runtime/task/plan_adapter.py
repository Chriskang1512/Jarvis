"""Safe migration bridge from legacy ExecutionPlan to TaskGraph."""

from dataclasses import dataclass, field, replace
from hashlib import sha256
import json

from jarvis.debug_trace import trace_event
from jarvis.runtime.task.graph import (
    NodeState,
    GraphValidationStage,
    InvalidTaskGraph,
    TaskGraph,
    TaskGraphCoordinator,
    TaskGraphValidator,
    TaskNode,
    TurnResult,
    TurnResultStatus,
)


@dataclass(frozen=True)
class PlanGraphComparison:
    """Privacy-safe equivalence result for one shadow conversion."""

    plan_id: str
    graph_id: str
    equivalent: bool
    checks: dict = field(default_factory=dict)
    mismatches: tuple[str, ...] = ()

    def to_dict(self):
        return {
            "plan_id": self.plan_id,
            "graph_id": self.graph_id,
            "equivalent": self.equivalent,
            "checks": dict(self.checks),
            "mismatches": list(self.mismatches),
        }


class ExecutionPlanAdapter:
    """Translate an ordered ExecutionPlan without changing its execution."""

    def to_task_graph(self, plan, task_id=""):
        steps = tuple(getattr(plan, "steps", ()) or ())
        node_ids = {
            step.index: f"STEP-{step.index}-{str(step.tool_name).upper()}"
            for step in steps
        }
        nodes = []
        previous_node_id = ""
        for step in steps:
            # ExecutionPlan is sequential even when it does not declare edges.
            dependencies = (previous_node_id,) if previous_node_id else ()
            nodes.append(
                TaskNode(
                    node_id=node_ids[step.index],
                    ability=str(step.tool_name),
                    operation=str(step.action),
                    dependencies=dependencies,
                    input=dict(getattr(step, "input_data", {}) or {}),
                    output_types={
                        "result": semantic_output_type(
                            str(step.tool_name), str(step.action)
                        )
                    },
                )
            )
            previous_node_id = node_ids[step.index]
        return TaskGraph(
            graph_id=f"GRAPH-{getattr(plan, 'id', '')}",
            task_id=str(task_id or getattr(plan, "id", "")),
            goal=str(getattr(plan, "raw_text", "") or getattr(plan, "id", "")),
            nodes=tuple(nodes),
        )

    def compare(self, plan, graph):
        steps = tuple(getattr(plan, "steps", ()) or ())
        nodes = tuple(graph.nodes)
        checks = {
            "step_count": len(steps) == len(nodes),
            "order": [step.index for step in steps]
            == [parse_node_index(node.node_id) for node in nodes],
            "abilities": [step.tool_name for step in steps]
            == [node.ability for node in nodes],
            "inputs": [input_fingerprint(step.input_data) for step in steps]
            == [input_fingerprint(node.input) for node in nodes],
            "sequential_dependencies": dependencies_match_order(nodes),
        }
        mismatches = tuple(name for name, passed in checks.items() if not passed)
        return PlanGraphComparison(
            plan_id=str(getattr(plan, "id", "")),
            graph_id=graph.graph_id,
            equivalent=not mismatches,
            checks=checks,
            mismatches=mismatches,
        )


class GraphExecutionObserver:
    """Project the authoritative TaskRunner lifecycle onto a TaskGraph."""

    def __init__(self, graph, coordinator, registry=None):
        self.graph = graph
        self.coordinator = coordinator
        self.registry = registry

    def step_started(self, task, step, input_data):
        if self.graph.task_id != task.id:
            self.graph = replace(self.graph, task_id=task.id)
        node_id = node_id_for_step(self.graph, step)
        self.graph = self.coordinator.set_node_state(
            self.graph, node_id, NodeState.RUNNING
        )
        trace_event(
            "runtime.task_graph.node_started",
            graph_id=self.graph.graph_id,
            task_id=task.id,
            node_id=node_id,
            ability=step.tool_name,
            action=step.action,
        )

    def step_finished(self, task, step, step_result, record):
        node_id = node_id_for_step(self.graph, step)
        status = (
            TurnResultStatus.WAIT_CONFIRM
            if is_confirm_required(step_result)
            else TurnResultStatus.COMPLETED
            if step_result.success
            else TurnResultStatus.FAILED
        )
        tool = self.registry.get(step.tool_name) if self.registry is not None else None
        provider = getattr(getattr(tool, "metadata", None), "provider", "")
        memory_refs = result_memory_refs(step_result)
        result = TurnResult(
            turn_id=f"{task.id}:{step.index}:{len(self.graph.node(node_id).turn_ids) + 1}",
            task_id=self.graph.task_id,
            node_id=node_id,
            status=status,
            output=getattr(step_result, "response", ""),
            memory_refs=memory_refs,
            error=getattr(step_result, "error", ""),
            provider_metadata={
                "provider": provider,
                "latency_ms": getattr(record, "duration_ms", 0),
            },
        )
        self.graph = self.coordinator.record_result(self.graph, result)


class GraphExecutor:
    """Validate and observe TaskGraph while TaskRunner remains authoritative."""

    def __init__(
        self,
        task_runner,
        registry=None,
        adapter=None,
        coordinator=None,
        permission_checker=None,
    ):
        self.task_runner = task_runner
        self.registry = registry
        self.adapter = adapter or ExecutionPlanAdapter()
        self.coordinator = coordinator or TaskGraphCoordinator()
        self.validator = TaskGraphValidator(
            ability_registry=registry,
            permission_checker=permission_checker,
        )

    def run(self, plan, **kwargs):
        runtime_task = kwargs.get("runtime_task")
        task_id = getattr(runtime_task, "id", "") or getattr(plan, "id", "")
        graph = self.adapter.to_task_graph(plan, task_id=task_id)
        comparison = self.adapter.compare(plan, graph)
        trace_event(
            "runtime.task_graph.shadow_compared",
            **comparison.to_dict(),
        )
        if not comparison.equivalent:
            raise ValueError(
                "EXECUTION_PLAN_TASK_GRAPH_MISMATCH:"
                + ",".join(comparison.mismatches)
            )
        if kwargs.get("confirmed"):
            graph = replace(
                graph,
                nodes=tuple(
                    replace(node, input={**node.input, "_confirmed": True})
                    for node in graph.nodes
                ),
            )
        report = self.validator.validate(graph)
        trace_event(
            "runtime.task_graph.validated",
            graph_id=graph.graph_id,
            task_id=graph.task_id,
            valid=report.valid,
            issue_count=len(report.issues),
            validation=report.to_dict(),
            graph=graph.to_dict(include_inputs=False),
        )
        hard_failures = tuple(
            issue
            for issue in report.issues
            if issue.blocking and issue.stage is not GraphValidationStage.PERMISSION
        )
        if hard_failures:
            raise InvalidTaskGraph(
                "; ".join(f"{issue.code}: {issue.message}" for issue in hard_failures)
            )
        graph = self.coordinator.start(graph)
        start_index = int(kwargs.get("start_index", 0) or 0)
        for node in graph.nodes[:start_index]:
            graph = self.coordinator.set_node_state(
                graph, node.node_id, NodeState.COMPLETED
            )
        graph = self.coordinator.refresh_ready(graph)
        observer = GraphExecutionObserver(graph, self.coordinator, self.registry)
        result = self.task_runner.run(plan, observer=observer, **kwargs)
        result = replace(
            result,
            plan_result=replace(
                result.plan_result,
                graph_id=observer.graph.graph_id,
            ),
        )
        trace_event(
            "runtime.task_graph.execution_completed",
            graph_id=observer.graph.graph_id,
            task_id=result.task.id,
            state=observer.graph.state.value,
            legacy_status=result.task.status.value,
            equivalent=comparison.equivalent,
        )
        return result


def node_id_for_step(graph, step):
    prefix = f"STEP-{step.index}-"
    return next(node.node_id for node in graph.nodes if node.node_id.startswith(prefix))


def parse_node_index(node_id):
    try:
        return int(str(node_id).split("-", 2)[1])
    except (IndexError, ValueError):
        return -1


def input_fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def dependencies_match_order(nodes):
    previous = ""
    for node in nodes:
        expected = (previous,) if previous else ()
        if tuple(node.dependencies) != expected:
            return False
        previous = node.node_id
    return True


def is_confirm_required(step_result):
    output = getattr(getattr(step_result, "tool_result", None), "output", None)
    metadata = getattr(output, "metadata", {}) or {}
    return metadata.get("permission") == "confirm_required"


def result_memory_refs(step_result):
    result = getattr(step_result, "tool_result", None)
    output = getattr(result, "output", None)
    metadata = getattr(output, "metadata", {}) or {}
    refs = metadata.get("memory_refs", ())
    return tuple(str(item) for item in (refs or ()))


def semantic_output_type(ability, action):
    """Return a conservative display contract for legacy plan steps."""
    key = (str(ability or "").lower(), str(action or "").lower())
    exact = {
        ("weather", "query"): "WeatherReport",
        ("calendar", "list"): "CalendarEvent",
        ("calendar", "query"): "CalendarEvent",
        ("calendar", "create"): "CalendarEvent",
        ("contacts", "list"): "Any",
        ("contacts", "query"): "Any",
        ("mail", "draft"): "EmailDraft",
        ("mail", "send"): "Any",
        ("memory", "remember"): "Any",
        ("memory", "recall"): "Any",
    }
    return exact.get(key, "Any")
