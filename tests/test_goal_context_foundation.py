import json
import unittest
from dataclasses import replace
from datetime import datetime

from jarvis.goals import (
    ConversationContextEngine,
    EntityReference,
    GoalParser,
    Provenance,
    ProvenanceSource,
    SemanticContext,
    SemanticSlot,
)
from jarvis.runtime.intent import IntentContext, IntentParseResult, StructuredIntent
from jarvis.runtime.task import ArtifactRef


NOW = datetime(2026, 7, 28, 10, 30)
INTENT_CONTEXT = IntentContext(
    session_id="test",
    current_date="2026-07-28",
    current_time="10:30:00",
    timezone="Asia/Seoul",
)


class StubIntentParser:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def parse(self, text, context):
        if self.error:
            raise self.error
        return self.result


def intent_result(*intents, source="rule", confidence=0.95):
    return IntentParseResult(
        success=True,
        intents=tuple(intents),
        source=source,
        confidence=confidence,
    )


class TestGoalContextFoundation(unittest.TestCase):
    def parser(self, result=None, engine=None):
        return GoalParser(
            intent_parser=StubIntentParser(
                result
                or intent_result(
                    StructuredIntent(
                        intent_id="weather.query",
                        ability="weather",
                        action="query",
                        confidence=0.95,
                    )
                )
            ),
            context_engine=engine,
            clock=lambda: NOW,
        )

    def test_explicit_single_request_normalizes_to_direct_goal(self):
        result = self.parser().parse(
            "내일 강릉 날씨 알려줘", intent_context=INTENT_CONTEXT
        )
        self.assertEqual("direct", result.route)
        self.assertEqual("weather", result.goal.context.domain)
        self.assertEqual("강릉", result.goal.context.slots["location"].value)
        self.assertEqual("2026-07-29", result.goal.context.slots["date"].value)

    def test_relative_date_time_and_duration_are_normalized(self):
        result = self.parser().parse(
            "내일 오후 3시에 한 시간 일정", intent_context=INTENT_CONTEXT
        )
        temporal = result.goal.context.temporal
        self.assertEqual("2026-07-29", temporal.date)
        self.assertEqual("15:00:00", temporal.time)
        self.assertEqual("PT1H", temporal.duration)

    def test_current_turn_entity_is_available_to_follow_up(self):
        engine = ConversationContextEngine()
        engine.save(
            "s",
            SemanticContext(
                domain="calendar",
                entities=(
                    EntityReference(
                        entity_type="event",
                        entity_id="evt-1",
                        value="아야와의 일정",
                    ),
                ),
            ),
        )
        result = self.parser(engine=engine).parse(
            "한 시간 늦춰줘", session_id="s", intent_context=INTENT_CONTEXT
        )
        self.assertEqual("evt-1", result.goal.context.entities[0].entity_id)
        self.assertEqual(
            ProvenanceSource.CONVERSATION_CONTEXT,
            result.goal.context.entities[0].provenance.source,
        )

    def test_previous_result_and_artifact_are_linked(self):
        engine = ConversationContextEngine()
        engine.record_result(
            "s",
            {"event_id": "evt-9"},
            result_id="result-9",
            result_type="calendar_event",
            artifact_refs=(
                ArtifactRef(
                    artifact_id="artifact-9",
                    artifact_type="CalendarEventRef",
                    uri="calendar://evt-9",
                ),
            ),
        )
        result = self.parser(engine=engine).parse(
            "아까 그 일정 한 시간 늦춰줘",
            session_id="s",
            intent_context=INTENT_CONTEXT,
        )
        previous = result.goal.context.previous_result
        self.assertEqual("result-9", previous.result_id)
        self.assertEqual("artifact-9", previous.artifact_refs[0]["artifact_id"])

    def test_explicit_location_overrides_user_default(self):
        result = self.parser().parse(
            "내일 서울 날씨 알려줘",
            intent_context=INTENT_CONTEXT,
            user_preferences={"location": "부산"},
        )
        slot = result.goal.context.slots["location"]
        self.assertEqual("서울", slot.value)
        self.assertEqual(ProvenanceSource.EXPLICIT_INPUT, slot.provenance.source)

    def test_current_explicit_input_overrides_previous_context(self):
        engine = ConversationContextEngine()
        engine.save(
            "s",
            SemanticContext(
                slots={
                    "location": SemanticSlot(
                        "location",
                        "제주",
                        provenance=Provenance(
                            ProvenanceSource.EXPLICIT_INPUT, turn_id="previous"
                        ),
                    )
                }
            ),
        )
        result = self.parser(engine=engine).parse(
            "서울 날씨 알려줘", session_id="s", intent_context=INTENT_CONTEXT
        )
        self.assertEqual("서울", result.goal.context.slots["location"].value)

    def test_ai_parser_exception_keeps_semantic_fallback(self):
        parser = GoalParser(
            intent_parser=StubIntentParser(error=RuntimeError("AI unavailable")),
            clock=lambda: NOW,
        )
        result = parser.parse("내일 서울 날씨 알려줘", intent_context=INTENT_CONTEXT)
        self.assertEqual("semantic_fallback", result.parser_source)
        self.assertEqual("weather", result.goal.context.domain)
        self.assertEqual("서울", result.goal.context.slots["location"].value)

    def test_semantic_context_json_round_trip(self):
        context = self.parser().parse(
            "내일 강릉 날씨 알려줘", intent_context=INTENT_CONTEXT
        ).goal.context
        restored = SemanticContext.from_dict(json.loads(json.dumps(context.to_dict())))
        self.assertEqual(context.to_dict(), restored.to_dict())

    def test_goal_specification_snapshot(self):
        goal = self.parser().parse(
            "내일 강릉 날씨 알려줘", intent_context=INTENT_CONTEXT
        ).goal
        snapshot = goal.to_dict()
        snapshot["goal_id"] = "<generated>"
        snapshot["created_at"] = "<generated>"
        snapshot["success_criteria"][0]["criterion_id"] = "<generated>"
        self.assertEqual(
            {
                "goal_id": "<generated>",
                "original_input": "내일 강릉 날씨 알려줘",
                "objective": "내일 강릉 날씨 알려줘",
                "constraints": [],
                "success_criteria": [
                    {
                        "description": "weather.query 결과가 확인됨",
                        "required": True,
                        "criterion_id": "<generated>",
                    }
                ],
                "context": snapshot["context"],
                "confidence": 1.0,
                "created_at": "<generated>",
            },
            snapshot,
        )

    def test_multiple_intents_route_to_goal_oriented(self):
        parsed = intent_result(
            StructuredIntent("calendar.list", "calendar", "list", confidence=0.9),
            StructuredIntent(
                "system.summarize",
                "system",
                "summarize",
                confidence=0.9,
                depends_on=0,
            ),
            source="ai",
            confidence=0.9,
        )
        result = self.parser(parsed).parse(
            "내일 오후 일정을 찾아서 요약해줘", intent_context=INTENT_CONTEXT
        )
        self.assertEqual("goal_oriented", result.route)
        self.assertEqual(2, len(result.goal.success_criteria))

    def test_context_is_isolated_by_user_conversation_and_session(self):
        engine = ConversationContextEngine()
        context = SemanticContext(
            slots={
                "location": SemanticSlot(
                    "location",
                    "서울",
                    provenance=Provenance(ProvenanceSource.EXPLICIT_INPUT),
                )
            }
        )
        engine.save(
            "session-1",
            context,
            user_id="user-1",
            conversation_id="conversation-1",
        )
        self.assertEqual(
            "서울",
            engine.get(
                "session-1",
                user_id="user-1",
                conversation_id="conversation-1",
            ).slots["location"].value,
        )
        self.assertEqual(
            {},
            engine.get(
                "session-1",
                user_id="user-1",
                conversation_id="conversation-2",
            ).slots,
        )
        self.assertEqual(
            {},
            engine.get(
                "session-1",
                user_id="user-2",
                conversation_id="conversation-1",
            ).slots,
        )

    def test_provenance_contains_audit_fields(self):
        result = self.parser().parse(
            "내일 강릉 날씨 알려줘", intent_context=INTENT_CONTEXT
        )
        provenance = result.goal.context.slots["location"].provenance.to_dict()
        self.assertEqual("EXPLICIT_INPUT", provenance["source"])
        self.assertIn("turn_id", provenance)
        self.assertIn("parser_id", provenance)
        self.assertIn("source_field", provenance)
        self.assertTrue(provenance["captured_at"])

    def test_goal_routing_uses_capability_dependency_and_mutation_signals(self):
        result = self.parser().parse(
            "날씨 보고 일정 바꿔줘", intent_context=INTENT_CONTEXT
        )
        self.assertEqual("goal_oriented", result.route)
        self.assertIn("multiple_capabilities", result.routing_reasons)
        self.assertIn("result_dependency", result.routing_reasons)
        self.assertIn("external_state_change", result.routing_reasons)

        incomplete = GoalParser(
            intent_parser=StubIntentParser(error=RuntimeError("no parse")),
            clock=lambda: NOW,
        ).parse(
            "내일 일정을 알려주고", intent_context=INTENT_CONTEXT
        )
        self.assertEqual("direct", incomplete.route)

    def test_single_external_change_is_goal_oriented(self):
        parsed = intent_result(
            StructuredIntent(
                "calendar.create", "calendar", "create", confidence=0.95
            )
        )
        result = self.parser(parsed).parse(
            "내일 오후 3시에 일정 등록해줘", intent_context=INTENT_CONTEXT
        )
        self.assertEqual("goal_oriented", result.route)
        self.assertEqual(("external_state_change",), result.routing_reasons)

    def test_inherited_entities_decay_and_context_has_lifecycle(self):
        engine = ConversationContextEngine(clock=lambda: NOW)
        engine.save(
            "s",
            SemanticContext(
                entities=(
                    EntityReference(
                        entity_type="event",
                        value="아야 일정",
                        entity_id="evt-1",
                        confidence=1.0,
                    ),
                )
            ),
        )
        first = self.parser(engine=engine).parse(
            "한 시간 늦춰줘", session_id="s", intent_context=INTENT_CONTEXT
        ).goal.context
        second = self.parser(engine=engine).parse(
            "다시 한 시간", session_id="s", intent_context=INTENT_CONTEXT
        ).goal.context
        self.assertAlmostEqual(0.9, first.entities[0].confidence)
        self.assertAlmostEqual(0.81, second.entities[0].confidence)
        self.assertEqual("conversation", second.lifecycle.scope)
        self.assertEqual("turn_window:12", second.lifecycle.expiration_policy)
        self.assertEqual(3, second.lifecycle.turn_index)

    def test_previous_result_does_not_cross_conversation_boundary(self):
        engine = ConversationContextEngine()
        engine.record_result(
            "s",
            {"event_id": "evt-1"},
            conversation_id="conversation-a",
        )
        result = self.parser(engine=engine).parse(
            "아까 그 일정 삭제해",
            session_id="s",
            conversation_id="conversation-b",
            intent_context=INTENT_CONTEXT,
        )
        self.assertIsNone(result.goal.context.previous_result)

    def test_context_expiration_values_are_configurable(self):
        engine = ConversationContextEngine(
            max_turns=4,
            confidence_decay=0.8,
            min_confidence=0.5,
            clock=lambda: NOW,
        )
        engine.save(
            "s",
            SemanticContext(
                entities=(
                    EntityReference(
                        entity_type="event",
                        value="아야 일정",
                        confidence=1.0,
                    ),
                )
            ),
        )
        context = self.parser(engine=engine).parse(
            "다시 보여줘", session_id="s", intent_context=INTENT_CONTEXT
        ).goal.context
        self.assertAlmostEqual(0.8, context.entities[0].confidence)
        self.assertEqual(0.8, context.lifecycle.confidence_decay)
        self.assertEqual("turn_window:4", context.lifecycle.expiration_policy)

    def test_invalid_context_expiration_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            ConversationContextEngine(max_turns=0)
        with self.assertRaises(ValueError):
            ConversationContextEngine(confidence_decay=0)
        with self.assertRaises(ValueError):
            ConversationContextEngine(min_confidence=1.1)


if __name__ == "__main__":
    unittest.main()
