"""Deterministic Sprint 5 Native Runtime smoke checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.weather import MockWeatherProvider
from jarvis.abilities.native.weather.ability import WeatherAbility
from jarvis.capability_planning import (
    CapabilityPlanValidator,
    CapabilityRegistryAdapter,
    ExecutionPlanSnapshotFactory,
    PlannerRequest,
    RulePlanner,
)
from jarvis.core.events import InMemoryEventBus
from jarvis.goals import GoalParser
from jarvis.graph_execution import CapabilityExecutionAdapter, GraphExecutor


class TimeoutOnceWeatherProvider:
    def __init__(self):
        self.inner = MockWeatherProvider()
        self.calls = 0

    def get_weather(self, query):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("injected provider timeout")
        return self.inner.get_weather(query)


class EventCollector:
    def __init__(self):
        self.events = []

    def handle(self, event):
        self.events.append(event)


def run(stage):
    provider = (
        TimeoutOnceWeatherProvider()
        if stage == "retry"
        else MockWeatherProvider()
    )
    ability_registry = AbilityRegistry()
    ability_registry.register(WeatherAbility(provider=provider))
    capability_snapshot = CapabilityRegistryAdapter().create_snapshot(
        ability_registry
    )
    parsed = GoalParser().parse(
        "내일 강릉 날씨 알려줘.",
        conversation_id="sprint5-smoke",
        session_id="sprint5-smoke",
        turn_id="sprint5-smoke-1",
    )
    planner = RulePlanner()
    request = PlannerRequest(
        parsed.goal,
        parsed.goal.context,
        capability_snapshot,
        correlation_id="sprint5-smoke",
    )
    planner_result = planner.plan(request)
    validator = CapabilityPlanValidator()
    report = validator.validate(
        planner_result.graph,
        capability_snapshot,
        goal=parsed.goal,
        mappings=planner_result.success_criteria_mappings,
        max_nodes=request.planning_policy.max_nodes,
    )
    snapshot = ExecutionPlanSnapshotFactory(validator).create(
        planner_result,
        capability_snapshot,
        goal=parsed.goal,
        mappings=planner_result.success_criteria_mappings,
        max_nodes=request.planning_policy.max_nodes,
    )
    collector = EventCollector()
    event_bus = InMemoryEventBus()
    event_bus.subscribe("*", collector.handle)
    executor = GraphExecutor(
        CapabilityExecutionAdapter(ability_registry),
        event_bus=event_bus,
        verification_enabled=True,
        retry_enabled=stage == "retry",
        replan_enabled=False,
        sleeper=lambda _: None,
    )
    execution = executor.execute(
        planner_result.graph,
        snapshot,
        report,
        goal=parsed.goal,
        success_criteria_mappings=planner_result.success_criteria_mappings,
        correlation_id="sprint5-smoke",
        binding_context={
            "context_slots": {
                key: slot.value
                for key, slot in parsed.goal.context.slots.items()
            }
        },
    )
    node = next(iter(execution.session.node_records.values()))
    waiting_entries = [
        {
            "event": item.event_type,
            "waitingReason": item.details.get("waiting_reason"),
            "waitingSince": item.details.get("waiting_since"),
        }
        for item in execution.session.timeline
        if item.event_type == "session_waiting"
    ]
    return {
        "stage": stage,
        "plannerStatus": planner_result.status.value,
        "graphId": planner_result.graph.graph_id,
        "snapshotId": snapshot.snapshot_id,
        "sessionId": execution.session.session_id,
        "eventOrder": [item.event_type for item in collector.events],
        "attemptCount": len(node.attempt_history),
        "idempotencyKeys": [
            item.idempotency_key for item in node.attempt_history
        ],
        "waitingEntries": waiting_entries,
        "providerCalls": execution.session.provider_calls,
        "retryCount": execution.summary.retry_count,
        "goalVerificationStatus": (
            execution.summary.goal_verification_status.value
        ),
        "outcome": execution.summary.outcome.value,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=("verification", "retry"),
        required=True,
    )
    args = parser.parse_args()
    print(json.dumps(run(args.stage), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
