"""Safe interactive Voice follow-up / Partial Replan runtime smoke."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.calendar import CalendarAbility, MockCalendarProvider
from jarvis.abilities.native.contacts import ContactAbility
from jarvis.capability_planning import (
    CapabilityRegistryAdapter,
    HybridPlanner,
    NativePlanningCoordinator,
)
from jarvis.core.events import InMemoryEventBus
from jarvis.graph_execution import CapabilityExecutionAdapter, GraphExecutor
from jarvis.voice import create_conversation_session
from jarvis.voice.pipeline import VoicePipeline


DEFAULT_COMMAND = "내일 오후 3시에 아야 만나는 일정 등록해줘"
DEFAULT_SELECTION = "2번"
DEFAULT_CONFIRMATION = "네"


class EventCollector:
    def __init__(self):
        self.events = []

    def handle(self, event):
        self.events.append(event.event_type)


def prompt(label, default):
    value = input(f'{label} [{default}]: ').strip()
    return value or default


def run(command, selection, confirmation):
    registry = AbilityRegistry()
    registry.register(ContactAbility(provider=None))
    registry.register(CalendarAbility(provider=MockCalendarProvider()))
    capability_snapshot = CapabilityRegistryAdapter().create_snapshot(registry)
    created_inputs = []
    provider_state = {}

    def search_contacts(_):
        return {
            "contacts": [
                {
                    "id": "smoke-aya-1",
                    "name": "아야 (테스트 후보 1)",
                    "email": "masked-1@example.invalid",
                },
                {
                    "id": "smoke-aya-2",
                    "name": "아야 (테스트 후보 2)",
                    "email": "masked-2@example.invalid",
                },
            ]
        }

    def create_calendar(inputs):
        event = {
            "id": "smoke-event-1",
            "date": inputs["date"],
            "time": inputs["time"],
            "start_time": inputs["time"],
            "title": inputs["title"],
            "participants": inputs.get("participants", []),
        }
        created_inputs.append(dict(inputs))
        provider_state["event"] = event
        return {"event": event}

    collector = EventCollector()
    event_bus = InMemoryEventBus()
    event_bus.subscribe("*", collector.handle)
    executor = GraphExecutor(
        CapabilityExecutionAdapter(
            handlers={
                "contacts.search": search_contacts,
                "calendar.create_event": create_calendar,
                "calendar.search_events": lambda _: provider_state["event"],
            }
        ),
        event_bus=event_bus,
        verification_enabled=True,
        retry_enabled=True,
        replan_enabled=True,
        sleeper=lambda _: None,
    )
    coordinator = NativePlanningCoordinator(
        capability_snapshot,
        planner=HybridPlanner(),
        native_execution_enabled=True,
        graph_executor=executor,
    )
    conversation = create_conversation_session(follow_up_timeout=30)
    conversation.start()
    pipeline = VoicePipeline(
        None,
        None,
        None,
        None,
        conversation_session=conversation,
        native_planning_coordinator=coordinator,
    )

    initial = pipeline.try_native_goal_planning(command)
    if initial is None or initial.pending_clarification is None:
        raise RuntimeError("The command did not enter Native NeedsUserInput.")
    old_session = initial.graph_execution_result.session
    conversation.set_pending_clarification(initial.pending_clarification)

    selection_reply = pipeline.try_pending_clarification_reply(selection)
    permission = conversation.get_pending_clarification()
    if not permission or permission.get("kind") != "native_graph_permission":
        raise RuntimeError(
            f"Candidate selection did not reach permission: {selection_reply}"
        )
    new_session = permission["session"]
    confirmation_reply = pipeline.try_pending_clarification_reply(confirmation)

    selected = (
        created_inputs[0].get("participants", [])
        if created_inputs
        else []
    )
    checks = {
        "needsUserInput": initial.status == "NeedsUserInput",
        "candidateSelectionAccepted": bool(selected),
        "selectedSecondCandidate": bool(
            selected and selected[0].get("id") == "smoke-aya-2"
        ),
        "newGraphId": old_session.graph_id != new_session.graph_id,
        "newSnapshotId": old_session.snapshot_id != new_session.snapshot_id,
        "newSessionId": old_session.session_id != new_session.session_id,
        "goalExecutionIdPreserved": (
            old_session.goal_execution_id == new_session.goal_execution_id
        ),
        "previousSessionLinked": (
            old_session.session_id in new_session.previous_session_ids
        ),
        "replanCompletedEvent": (
            "runtime.execution.replan_completed" in collector.events
        ),
        "sessionCompletedEvent": (
            "runtime.execution.session_completed" in collector.events
        ),
        "clarificationCleared": (
            conversation.get_pending_clarification() is None
        ),
    }
    return {
        "passed": all(checks.values()),
        "mode": "safe_mock_providers_real_runtime",
        "inputs": {
            "command": command,
            "selection": selection,
            "confirmation": confirmation,
        },
        "replies": {
            "initial": initial.response,
            "selection": selection_reply,
            "confirmation": confirmation_reply,
        },
        "lineage": {
            "oldGraphId": old_session.graph_id,
            "newGraphId": new_session.graph_id,
            "oldSnapshotId": old_session.snapshot_id,
            "newSnapshotId": new_session.snapshot_id,
            "oldSessionId": old_session.session_id,
            "newSessionId": new_session.session_id,
            "goalExecutionId": new_session.goal_execution_id,
        },
        "selectedCandidateId": (
            selected[0].get("id", "") if selected else ""
        ),
        "checks": checks,
        "eventOrder": collector.events,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Safe Sprint 5 Voice Partial Replan smoke"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Use the recommended three utterances without prompting.",
    )
    args = parser.parse_args()
    if args.auto:
        values = (
            DEFAULT_COMMAND,
            DEFAULT_SELECTION,
            DEFAULT_CONFIRMATION,
        )
    else:
        print("Jarvis Sprint 5 Voice E2E Safe Smoke")
        print("Enter를 누르면 대괄호 안의 권장 멘트를 사용합니다.")
        values = (
            prompt("1. 최초 명령", DEFAULT_COMMAND),
            prompt("2. 후보 선택", DEFAULT_SELECTION),
            prompt("3. 변경 승인", DEFAULT_CONFIRMATION),
        )
    result = run(*values)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
