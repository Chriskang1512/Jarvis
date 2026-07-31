"""Rule-first planner selection and bounded AI repair loop."""

from __future__ import annotations

from dataclasses import replace
from time import perf_counter

from jarvis.capability_planning.models import (
    PlannerRequest,
    PlanningPolicy,
    PlannerStatus,
    PlannerType,
)
from jarvis.capability_planning.rule_planner import RulePlanner
from jarvis.capability_planning.validation import CapabilityPlanValidator


class HybridPlanner:
    def __init__(self, rule_planner=None, ai_planner=None, validator=None):
        self.validator = validator or CapabilityPlanValidator()
        self.rule_planner = rule_planner or RulePlanner(self.validator)
        self.ai_planner = ai_planner

    def plan(self, request):
        rule_result = self.rule_planner.plan(request)
        if rule_result.status in {
            PlannerStatus.PLANNED,
            PlannerStatus.NEEDS_USER_INPUT,
        }:
            return rule_result
        if self.ai_planner is None:
            return rule_result
        ai_result = self.ai_planner.plan(request)
        if ai_result.status == PlannerStatus.PLANNED:
            return ai_result
        if ai_result.status != PlannerStatus.INVALID or ai_result.graph is None:
            return ai_result
        graph = ai_result.graph
        mappings = ai_result.success_criteria_mappings
        last_report = None
        for attempt in range(1, request.planning_policy.max_repair_attempts + 1):
            last_report = self.validator.validate(
                graph,
                request.capability_snapshot,
                goal=request.goal,
                mappings=mappings,
                max_nodes=request.planning_policy.max_nodes,
            )
            if last_report.is_valid:
                return repaired_result(ai_result, graph, attempt - 1, last_report)
            try:
                repaired = self.ai_planner.repair(
                    request, graph, last_report, attempt
                )
            except Exception:
                repaired = None
            if repaired is None:
                break
            graph = repaired
            from jarvis.capability_planning.ai_planner import mappings_from_graph

            mappings = mappings_from_graph(graph)
            report = self.validator.validate(
                graph,
                request.capability_snapshot,
                goal=request.goal,
                mappings=mappings,
                max_nodes=request.planning_policy.max_nodes,
            )
            if report.is_valid:
                return repaired_result(ai_result, graph, attempt, report, mappings)
            last_report = report
        diagnostics = replace(
            ai_result.diagnostics,
            repair_count=request.planning_policy.max_repair_attempts,
            validation_issues=tuple(
                issue.code for issue in (last_report.errors if last_report else ())
            ),
        )
        return replace(
            ai_result,
            status=PlannerStatus.FAILED,
            graph=None,
            diagnostics=diagnostics,
        )

    def replan(self, request):
        """Plan the remaining goal against the newest capability snapshot."""
        goal = request.goal_specification
        if request.user_supplied_clarification:
            answer = str(request.user_supplied_clarification).strip()
            goal = replace(
                goal,
                original_input=f"{goal.original_input} {answer}".strip(),
                objective=f"{goal.objective} ({answer})",
            )
        planner_request = PlannerRequest(
            goal=goal,
            semantic_context=request.current_conversation_context
            or goal.context,
            capability_snapshot=request.capability_registry_snapshot,
            planning_policy=PlanningPolicy(max_nodes=request.max_replan_nodes),
            existing_graph=request.current_graph,
            correlation_id=request.correlation_id,
        )
        return self.plan(planner_request)


def repaired_result(base, graph, repair_count, report, mappings=None):
    diagnostics = replace(
        base.diagnostics,
        repair_count=repair_count,
        validation_issues=tuple(issue.code for issue in report.errors),
    )
    return replace(
        base,
        status=PlannerStatus.PLANNED,
        graph=graph,
        diagnostics=diagnostics,
        success_criteria_mappings=mappings
        if mappings is not None
        else base.success_criteria_mappings,
    )
