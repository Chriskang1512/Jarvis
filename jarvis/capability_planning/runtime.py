"""Runtime bridge from semantic goals to validated native plans."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.capability_planning.execution_snapshot import (
    ExecutionPlanSnapshot,
    ExecutionPlanSnapshotFactory,
)
from jarvis.capability_planning.models import (
    PlannerRequest,
    PlannerResult,
    PlannerStatus,
)
from jarvis.capability_planning.validation import CapabilityPlanValidator
from jarvis.debug_trace import trace_event
from jarvis.goals import GoalParser


@dataclass(frozen=True)
class NativePlanningOutcome:
    request_route: str
    result: PlannerResult
    execution_plan_snapshot: ExecutionPlanSnapshot | None = None
    validation_report: object = None
    execution_result: object = None
    goal_specification: object = None


class NativePlanningCoordinator:
    """Plan goal-oriented requests without executing their graph."""

    def __init__(
        self,
        capability_snapshot,
        *,
        planner,
        goal_parser=None,
        user_preferences=None,
        native_execution_enabled=False,
        graph_executor=None,
    ):
        self.capability_snapshot = capability_snapshot
        self.planner = planner
        self.goal_parser = goal_parser or GoalParser()
        self.user_preferences = dict(user_preferences or {})
        self.native_execution_enabled = bool(native_execution_enabled)
        self.graph_executor = graph_executor
        self.execution_snapshot_factory = ExecutionPlanSnapshotFactory(
            getattr(planner, "validator", None)
            or CapabilityPlanValidator()
        )

    def plan(
        self,
        text,
        *,
        user_id="local",
        conversation_id="default",
        session_id="default",
        turn_id="",
    ):
        parsed = self.goal_parser.parse(
            text,
            user_id=user_id,
            conversation_id=conversation_id,
            session_id=session_id,
            turn_id=turn_id,
            user_preferences=self.user_preferences,
        )
        native_reasons = {
            "conditional_branch",
            "multiple_capabilities",
            "result_dependency",
            "previous_result_dependency",
            "pause_or_resume",
            "external_state_change",
        }
        should_use_native = bool(
            native_reasons.intersection(parsed.routing_reasons)
        )
        if parsed.route != "goal_oriented" or not should_use_native:
            trace_event(
                "runtime.goal_router.routed",
                request_route="direct",
                routing_reasons=list(parsed.routing_reasons),
                native_execution_enabled=self.native_execution_enabled,
            )
            return None

        trace_event(
            "runtime.goal_router.routed",
            request_route="goal_oriented",
            routing_reasons=list(parsed.routing_reasons),
            native_execution_enabled=self.native_execution_enabled,
        )
        request = PlannerRequest(
            goal=parsed.goal,
            semantic_context=parsed.goal.context,
            capability_snapshot=self.capability_snapshot,
            correlation_id=conversation_id,
        )
        result = self.planner.plan(request)
        if (
            result.status == PlannerStatus.UNSUPPORTED
            and set(parsed.routing_reasons) == {"external_state_change"}
        ):
            trace_event(
                "runtime.goal_router.routed",
                request_route="direct",
                routing_reasons=list(parsed.routing_reasons),
                native_execution_enabled=self.native_execution_enabled,
                native_fallback_reason="unsupported_single_mutation",
            )
            return None
        graph = result.graph
        diagnostics = result.diagnostics
        execution_plan_snapshot = None
        validation_report = None
        execution_result = None
        if result.status == PlannerStatus.PLANNED:
            validation_report = self.execution_snapshot_factory.validator.validate(
                graph,
                self.capability_snapshot,
                goal=parsed.goal,
                mappings=result.success_criteria_mappings,
                max_nodes=request.planning_policy.max_nodes,
            )
            execution_plan_snapshot = (
                self.execution_snapshot_factory.create(
                    result,
                    self.capability_snapshot,
                    goal=parsed.goal,
                    mappings=result.success_criteria_mappings,
                    max_nodes=request.planning_policy.max_nodes,
                )
            )
            if self.native_execution_enabled:
                if self.graph_executor is None:
                    raise RuntimeError(
                        "Native execution is enabled without GraphExecutor."
                    )
                execution_result = self.graph_executor.execute(
                    graph,
                    execution_plan_snapshot,
                    validation_report,
                    correlation_id=conversation_id,
                    binding_context={
                        "context_slots": {
                            key: item.value
                            for key, item in parsed.goal.context.slots.items()
                        }
                    },
                    goal=parsed.goal,
                    success_criteria_mappings=(
                        result.success_criteria_mappings
                    ),
                )
                from jarvis.graph_execution import ReplanController

                replan_controller = ReplanController(
                    self.planner,
                    validator=self.execution_snapshot_factory.validator,
                    snapshot_factory=self.execution_snapshot_factory,
                    event_bus=getattr(self.graph_executor, "event_bus", None),
                )
                replan_reasons = []
                while (
                    getattr(execution_result, "requires_replan", False)
                    and getattr(
                        self.graph_executor, "replan_enabled", False
                    )
                    and not execution_result.replan_trigger.user_input_required
                    and len(replan_reasons) < replan_controller.max_attempts
                ):
                    decision = replan_controller.build_request(
                        goal=parsed.goal,
                        graph=graph,
                        snapshot=execution_plan_snapshot,
                        session=execution_result.session,
                        trigger=execution_result.replan_trigger,
                        capability_snapshot=self.capability_snapshot,
                        conversation_context=parsed.goal.context,
                        correlation_id=conversation_id,
                        attempt_number=len(replan_reasons),
                        previous_failure_reasons=tuple(replan_reasons),
                    )
                    replanned = replan_controller.replan(decision)
                    if not replanned.succeeded:
                        break
                    replan_reasons.append(
                        execution_result.replan_trigger.reason
                    )
                    graph = replanned.graph
                    execution_plan_snapshot = replanned.snapshot
                    validation_report = replanned.validation_report
                    result = replanned.planner_result
                    execution_result = self.graph_executor.execute(
                        graph,
                        execution_plan_snapshot,
                        validation_report,
                        correlation_id=conversation_id,
                        binding_context={
                            "context_slots": {
                                key: item.value
                                for key, item in parsed.goal.context.slots.items()
                            },
                            **replanned.binding_context,
                        },
                        session=replanned.session,
                        goal=parsed.goal,
                        success_criteria_mappings=(
                            result.success_criteria_mappings
                        ),
                    )
        trace_event(
            "runtime.native_planner.completed",
            request_route="goal_oriented",
            planner_type=result.planner_type.value,
            capability_snapshot_id=result.capability_snapshot_id,
            registry_hash=self.capability_snapshot.registry_hash,
            planner_status=result.status.value,
            selected_capabilities=list(
                diagnostics.selected_capabilities if diagnostics else ()
            ),
            graph_id=getattr(graph, "graph_id", ""),
            graph_node_count=len(getattr(graph, "nodes", ()) or ()),
            validation_status="Valid" if graph is not None else "NotValidated",
            native_execution_enabled=self.native_execution_enabled,
            execution_plan_snapshot_id=(
                execution_plan_snapshot.snapshot_id
                if execution_plan_snapshot
                else ""
            ),
            graph_hash=(
                execution_plan_snapshot.graph_hash
                if execution_plan_snapshot
                else ""
            ),
            validation_hash=(
                execution_plan_snapshot.validation_hash
                if execution_plan_snapshot
                else ""
            ),
            planning_confidence=(
                execution_plan_snapshot.planning_confidence
                if execution_plan_snapshot
                else 0.0
            ),
            missing_inputs=[
                item.field for item in result.missing_inputs
            ],
        )
        return NativePlanningOutcome(
            "goal_oriented",
            result,
            execution_plan_snapshot,
            validation_report,
            execution_result,
            parsed.goal,
        )
