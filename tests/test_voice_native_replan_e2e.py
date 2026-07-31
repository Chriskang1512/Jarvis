import unittest

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


class EventCollector:
    def __init__(self):
        self.events = []

    def handle(self, event):
        self.events.append(event.event_type)


class TestVoiceNativeReplanEndToEnd(unittest.TestCase):
    def test_second_candidate_resumes_replans_and_executes_selected_contact(self):
        registry = AbilityRegistry()
        registry.register(ContactAbility(provider=None))
        registry.register(CalendarAbility(provider=MockCalendarProvider()))
        capability_snapshot = CapabilityRegistryAdapter().create_snapshot(
            registry
        )
        created_inputs = []
        provider_state = {}

        def search_contacts(_):
            return {
                "contacts": [
                    {"id": "aya-1", "name": "Aya A"},
                    {"id": "aya-2", "name": "Aya B"},
                ]
            }

        def create_calendar(inputs):
            event = {
                "id": "event-1",
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

        initial = pipeline.try_native_goal_planning(
            "내일 오후 3시에 아야 만나는 일정 등록해줘"
        )

        self.assertEqual("native_replan_required", initial.error)
        self.assertEqual("NeedsUserInput", initial.status)
        self.assertEqual(
            "native_graph_replan",
            initial.pending_clarification["kind"],
        )
        previous_session = initial.graph_execution_result.session
        conversation.set_pending_clarification(
            initial.pending_clarification
        )

        selection_reply = pipeline.try_pending_clarification_reply("2번")

        self.assertIn("사용자 확인", selection_reply)
        permission = conversation.get_pending_clarification()
        self.assertEqual("native_graph_permission", permission["kind"])
        replanned_session = permission["session"]
        self.assertEqual(
            previous_session.goal_execution_id,
            replanned_session.goal_execution_id,
        )
        self.assertIn(
            previous_session.session_id,
            replanned_session.previous_session_ids,
        )
        self.assertNotEqual(
            previous_session.graph_id,
            replanned_session.graph_id,
        )
        self.assertNotEqual(
            previous_session.snapshot_id,
            replanned_session.snapshot_id,
        )

        final_reply = pipeline.try_pending_clarification_reply("네")

        self.assertIn("event-1", final_reply)
        self.assertEqual(
            [{"id": "aya-2", "name": "Aya B"}],
            created_inputs[0]["participants"],
        )
        self.assertIsNone(conversation.get_pending_clarification())
        self.assertIn(
            "runtime.execution.replan_completed",
            collector.events,
        )
        self.assertIn(
            "runtime.execution.session_completed",
            collector.events,
        )


if __name__ == "__main__":
    unittest.main()
