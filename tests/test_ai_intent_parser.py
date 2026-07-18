import json
import os
import unittest

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.integration.n8n import N8nIntegrationAbility
from jarvis.abilities.native.reminder import ReminderAbility
from jarvis.abilities.native.weather import WeatherAbility
from jarvis.abilities.native.memory import MemoryAbility
from jarvis.abilities.native.calendar import CalendarAbility
from jarvis.integrations.n8n.provider import MockIntegrationBridge
from jarvis.runtime.intent import AIIntentParser, HybridIntentParser, IntentContext, IntentMetricsCollector, IntentValidator, get_intent_metrics
from jarvis.runtime.intent.errors import (
    FORBIDDEN_PROVIDER_OR_URL,
    INVALID_ACTION_FOR_ABILITY,
    INVALID_DATE_TIME,
    MISSING_REQUIRED_PARAMETER,
)
from jarvis.runtime.intent.models import IntentParseResult, StructuredIntent
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.brain import IntentRuntime
from jarvis.tools import ToolRegistry
from jarvis.voice.pipeline import VoicePipeline


class TestAIIntentParserSprint8(unittest.TestCase):
    """Sprint 8 AI Intent Parser / NLU layer tests."""

    def test_ai_parser_maps_integration_health_variants(self):
        """Different health phrases become integration.health."""
        provider = MappingProvider(
            {
                "연동 상태 확인해줘": integration_health_payload(),
                "외부 자동화 상태 봐줘": integration_health_payload(),
                "브리지 살아 있어?": integration_health_payload(),
                "n8n 연결 괜찮아?": integration_health_payload(),
            }
        )
        parser = AIIntentParser(provider=provider, enabled=True)

        for text in ["연동 상태 확인해줘", "외부 자동화 상태 봐줘", "브리지 살아 있어?", "n8n 연결 괜찮아?"]:
            with self.subTest(text=text):
                result = parser.parse(text, test_context())
                validated = IntentValidator().validate_result(result)

                self.assertTrue(validated.success)
                self.assertEqual(validated.first_intent.intent_id, "integration.health")
                self.assertEqual(validated.first_intent.ability, "integration_n8n")
                self.assertEqual(validated.first_intent.action, "health")

    def test_ai_parser_maps_integration_execute_variants(self):
        """Send/echo phrases become integration.execute with workflow payload."""
        provider = MappingProvider(
            {
                "외부 자동화로 안녕하세요 보내줘": integration_execute_payload("system.echo", "안녕하세요"),
                "자동화 브리지로 테스트 메시지 보내줘": integration_execute_payload("notification.test", "테스트 메시지"),
                "system echo로 안녕하세요 보내줘": integration_execute_payload("system.echo", "안녕하세요"),
            }
        )
        parser = AIIntentParser(provider=provider, enabled=True)

        for text, workflow_key in [
            ("외부 자동화로 안녕하세요 보내줘", "system.echo"),
            ("자동화 브리지로 테스트 메시지 보내줘", "notification.test"),
            ("system echo로 안녕하세요 보내줘", "system.echo"),
        ]:
            with self.subTest(text=text):
                result = IntentValidator().validate_result(parser.parse(text, test_context()))

                self.assertTrue(result.success)
                self.assertEqual(result.first_intent.intent_id, "integration.execute")
                self.assertEqual(result.first_intent.parameters["workflow_key"], workflow_key)

    def test_ai_parser_normalizes_dotted_action_values(self):
        """AI output using intent_id as action is normalized before validation."""
        provider = StaticProvider(
            {
                "intents": [
                    {
                        "intent_id": "integration.health",
                        "ability": "integration_n8n",
                        "action": "integration.health",
                        "confidence": 0.92,
                    }
                ]
            }
        )

        result = IntentValidator().validate_result(AIIntentParser(provider=provider, enabled=True).parse("브리지 살아 있어?", test_context()))

        self.assertTrue(result.success)
        self.assertEqual(result.first_intent.action, "health")

    def test_ai_parser_uses_compact_prompt_and_generation_limits(self):
        """AI parser sends compact prompts and intent-specific generation caps."""
        previous_limit = os.environ.get("JARVIS_AI_INTENT_MAX_OUTPUT_TOKENS")
        previous_reasoning = os.environ.get("JARVIS_AI_INTENT_REASONING_EFFORT")
        previous_verbosity = os.environ.get("JARVIS_AI_INTENT_VERBOSITY")
        os.environ["JARVIS_AI_INTENT_MAX_OUTPUT_TOKENS"] = "123"
        os.environ["JARVIS_AI_INTENT_REASONING_EFFORT"] = "minimal"
        os.environ["JARVIS_AI_INTENT_VERBOSITY"] = "low"
        provider = CapturingIntentProvider(integration_health_payload())

        try:
            result = AIIntentParser(provider=provider, enabled=True).parse("bridge alive?", test_context())
        finally:
            restore_env("JARVIS_AI_INTENT_MAX_OUTPUT_TOKENS", previous_limit)
            restore_env("JARVIS_AI_INTENT_REASONING_EFFORT", previous_reasoning)
            restore_env("JARVIS_AI_INTENT_VERBOSITY", previous_verbosity)

        prompt = json.loads(provider.prompt)
        self.assertTrue(result.success)
        self.assertEqual(provider.options["max_output_tokens"], 123)
        self.assertEqual(provider.options["reasoning_effort"], "minimal")
        self.assertEqual(provider.options["verbosity"], "low")
        self.assertIn("calendar.create", prompt["allowed"])
        self.assertNotIn("schema", prompt)
        self.assertNotIn("session_id", prompt["context"])

    def test_ai_parser_blocks_truncated_provider_output(self):
        """Token-limit stops are treated as unsafe parser failures."""
        provider = CapturingIntentProvider(integration_health_payload(), finish_reason="length")
        result = AIIntentParser(provider=provider, enabled=True).parse("bridge alive?", test_context())

        self.assertFalse(result.success)
        self.assertTrue(result.requires_clarification)
        self.assertTrue(result.truncated)
        self.assertEqual(result.finish_reason, "length")

    def test_ai_parser_maps_calendar_reminder_and_memory(self):
        """Calendar, reminder, and memory phrases become structured intents."""
        provider = MappingProvider(
            {
                "내일 세 시에 아야 만나기로 잡아줘": calendar_create_payload(),
                "내일 오후 세 시 일정 하나 넣어줘": calendar_create_payload(title="일정"),
                "아야랑 내일 세 시 약속 등록해줘": calendar_create_payload(title="아야 약속"),
                "1분 뒤 물 마시라고 해줘": reminder_create_payload(),
                "잠시 후 물 마시라고 알려줘": reminder_create_payload(relative_minutes=1),
                "1분 있다가 물 마시는 거 잊지 않게 해줘": reminder_create_payload(),
                "아야 생일은 2월 28일이야 기억해": memory_remember_payload(),
                "아야 생일 저장해둬": memory_remember_payload(),
                "앞으로 아야 생일은 2월 28일로 기억해": memory_remember_payload(),
            }
        )
        parser = AIIntentParser(provider=provider, enabled=True)
        validator = IntentValidator()

        calendar = validator.validate_result(parser.parse("내일 세 시에 아야 만나기로 잡아줘", test_context()))
        reminder = validator.validate_result(parser.parse("1분 뒤 물 마시라고 해줘", test_context()))
        memory = validator.validate_result(parser.parse("아야 생일은 2월 28일이야 기억해", test_context()))

        self.assertEqual(calendar.first_intent.key, "calendar.create")
        self.assertEqual(calendar.first_intent.parameters["time"], "15:00")
        self.assertEqual(reminder.first_intent.key, "reminder.create")
        self.assertEqual(reminder.first_intent.parameters["relative_minutes"], 1)
        self.assertEqual(memory.first_intent.key, "memory.remember")
        self.assertEqual(memory.first_intent.parameters["key"], "relationship.aya.birthday")

        for text in ["내일 오후 세 시 일정 하나 넣어줘", "아야랑 내일 세 시 약속 등록해줘"]:
            self.assertEqual(validator.validate_result(parser.parse(text, test_context())).first_intent.key, "calendar.create")

        for text in ["잠시 후 물 마시라고 알려줘", "1분 있다가 물 마시는 거 잊지 않게 해줘"]:
            self.assertEqual(validator.validate_result(parser.parse(text, test_context())).first_intent.key, "reminder.create")

        for text in ["아야 생일 저장해둬", "앞으로 아야 생일은 2월 28일로 기억해"]:
            self.assertEqual(validator.validate_result(parser.parse(text, test_context())).first_intent.key, "memory.remember")

    def test_ai_parser_returns_clarification(self):
        """Missing calendar time asks a question instead of guessing."""
        provider = StaticProvider(
            {
                "requires_clarification": True,
                "clarification_question": "내일 몇 시에 등록할까요?",
                "intents": [
                    {
                        "intent_id": "calendar.create",
                        "ability": "calendar",
                        "action": "create",
                        "parameters": {"date": "2026-07-14", "title": "일정"},
                        "confidence": 0.82,
                    }
                ],
            }
        )
        result = AIIntentParser(provider=provider, enabled=True).parse("내일 일정 등록해줘", test_context())

        self.assertTrue(result.requires_clarification)
        self.assertEqual(result.clarification_question, "내일 몇 시에 등록할까요?")

    def test_ai_parser_multi_intent_calendar_and_reminder(self):
        """AI can return multiple structured intents without executing them."""
        provider = StaticProvider(
            {
                "intents": [
                    {
                        "intent_id": "calendar.create",
                        "ability": "calendar",
                        "action": "create",
                        "parameters": {"date": "2026-07-14", "time": "15:00", "title": "아야 만나기"},
                        "confidence": 0.94,
                    },
                    {
                        "intent_id": "reminder.create",
                        "ability": "reminder",
                        "action": "create",
                        "parameters": {"remind_before_minutes": 30, "title": "아야 만나기"},
                        "depends_on": 0,
                        "confidence": 0.91,
                    },
                ]
            }
        )
        result = IntentValidator().validate_result(AIIntentParser(provider=provider, enabled=True).parse("multi", test_context()))

        self.assertTrue(result.success)
        self.assertEqual(len(result.intents), 2)
        self.assertEqual(result.intents[1].depends_on, 0)

    def test_planner_accepts_list_depends_on_from_ai_output(self):
        """AI list-form depends_on values do not crash the Planner."""
        dispatcher = create_dispatcher(
            HybridIntentParser(
                ai_parser=AIIntentParser(
                    provider=StaticProvider(
                        {
                            "intents": [
                                {
                                    "intent_id": "integration.health",
                                    "ability": "integration_n8n",
                                    "action": "health",
                                    "parameters": {"workflow_key": "system.health"},
                                    "confidence": 0.91,
                                },
                                {
                                    "intent_id": "integration.health",
                                    "ability": "integration_n8n",
                                    "action": "health",
                                    "parameters": {"workflow_key": "system.health"},
                                    "depends_on": [0],
                                    "confidence": 0.91,
                                },
                            ]
                        }
                    ),
                    enabled=True,
                )
            )
        )

        plan = dispatcher.create_plan("bridge health twice")

        self.assertEqual(plan.step_count, 2)
        self.assertEqual(plan.steps[1].depends_on, (1,))

    def test_planner_converts_multi_intent_to_two_steps(self):
        """Runtime Planner converts an AI multi-intent result into ordered steps."""
        dispatcher = create_dispatcher(
            HybridIntentParser(
                ai_parser=AIIntentParser(
                    provider=StaticProvider(
                        {
                            "intents": [
                                {
                                    "intent_id": "calendar.create",
                                    "ability": "calendar",
                                    "action": "create",
                                    "parameters": {"date": "2026-07-14", "time": "15:00", "title": "아야 만나기"},
                                    "confidence": 0.94,
                                },
                                {
                                    "intent_id": "reminder.create",
                                    "ability": "reminder",
                                    "action": "create",
                                    "parameters": {"remind_before_minutes": 30, "title": "아야 만나기"},
                                    "depends_on": 0,
                                    "confidence": 0.91,
                                },
                            ]
                        }
                    ),
                    enabled=True,
                )
            )
        )
        plan = dispatcher.create_plan("아야 만나기 잡고 30분 전에 알려줘")

        self.assertEqual(plan.step_count, 2)
        self.assertEqual(plan.steps[0].tool_name, "calendar")
        self.assertEqual(plan.steps[1].tool_name, "reminder")
        self.assertEqual(plan.steps[1].depends_on, (1,))

    def test_validator_blocks_invalid_ai_output(self):
        """Invalid AI output is rejected before planning."""
        validator = IntentValidator()

        cases = [
            (StructuredIntent("bad", "unknown", "query", confidence=0.99), INVALID_ACTION_FOR_ABILITY),
            (StructuredIntent("bad", "calendar", "send_email", confidence=0.99), INVALID_ACTION_FOR_ABILITY),
            (StructuredIntent("bad", "calendar", "create", parameters={"date": "2026-07-14"}, confidence=0.99), MISSING_REQUIRED_PARAMETER),
            (
                StructuredIntent(
                    "bad",
                    "calendar",
                    "create",
                    parameters={"date": "tomorrow", "time": "15:00", "title": "x"},
                    confidence=0.99,
                ),
                INVALID_DATE_TIME,
            ),
            (
                StructuredIntent(
                    "bad",
                    "integration_n8n",
                    "execute",
                    parameters={"workflow_key": "system.echo", "payload": {"url": "https://evil.example"}},
                    confidence=0.99,
                ),
                FORBIDDEN_PROVIDER_OR_URL,
            ),
        ]

        for intent, error_code in cases:
            with self.subTest(error_code=error_code):
                result = validator.validate_result(IntentParseResult(success=True, intents=(intent,), source="ai", confidence=0.99))
                self.assertFalse(result.success)
                self.assertEqual(result.error_code, error_code)

    def test_validator_blocks_ungrounded_todo_create(self):
        """AI cannot invent Todo creation when the transcript has no create signal."""
        validator = IntentValidator()
        unsafe = StructuredIntent(
            "todo.create",
            "todo",
            "create",
            parameters={"title": "우유 사기"},
            confidence=0.91,
            source="ai",
            raw_text="목록보기에 우유 사기",
            normalized_text="목록보기에 우유 사기",
        )
        safe = StructuredIntent(
            "todo.create",
            "todo",
            "create",
            parameters={"title": "우유 사기"},
            confidence=0.91,
            source="ai",
            raw_text="우유 사기 추가해",
            normalized_text="우유 사기 추가해",
        )

        unsafe_result = validator.validate_result(IntentParseResult(success=True, intents=(unsafe,), source="ai", confidence=0.91))
        safe_result = validator.validate_result(IntentParseResult(success=True, intents=(safe,), source="ai", confidence=0.91))

        self.assertFalse(unsafe_result.success)
        self.assertEqual(unsafe_result.error_code, MISSING_REQUIRED_PARAMETER)
        self.assertTrue(safe_result.success)
        self.assertEqual(safe_result.first_intent.key, "todo.create")

    def test_conditional_execution_is_not_planned(self):
        """Unsupported conditional commands stay blocked."""
        provider = StaticProvider({"unsupported_reason": "conditional_execution", "intents": []})
        parser = HybridIntentParser(ai_parser=AIIntentParser(provider=provider, enabled=True))
        result = parser.parse("내일 비 오면 우산 챙기라고 알려줘", test_context())

        self.assertFalse(result.success)
        self.assertEqual(result.unsupported_reason, "conditional_execution")

    def test_confidence_policy_clarifies_low_confidence_write(self):
        """Low-confidence write actions ask for clarification."""
        provider = StaticProvider(
            {
                "intents": [
                    {
                        "intent_id": "calendar.create",
                        "ability": "calendar",
                        "action": "create",
                        "parameters": {"date": "2026-07-14", "time": "15:00", "title": "회의"},
                        "confidence": 0.78,
                    }
                ]
            }
        )
        result = HybridIntentParser(ai_parser=AIIntentParser(provider=provider, enabled=True)).parse("애매한 일정", test_context())

        self.assertTrue(result.requires_clarification)

    def test_ai_failure_falls_back_to_rule_when_possible(self):
        """Provider failures do not break high-confidence rule commands."""
        parser = HybridIntentParser(ai_parser=AIIntentParser(provider=FailingProvider(), enabled=True))
        result = parser.parse("오늘 강릉 날씨 알려줘", test_context())

        self.assertTrue(result.success)
        self.assertEqual(result.source, "rule")

    def test_hybrid_uses_rule_for_high_confidence_and_ai_for_low_confidence(self):
        """Hybrid keeps high-confidence rules and falls back to AI otherwise."""
        provider = MappingProvider({"브리지 살아 있어?": integration_health_payload()})
        parser = HybridIntentParser(ai_parser=AIIntentParser(provider=provider, enabled=True))

        rule_result = parser.parse("오늘 강릉 날씨 알려줘", test_context())
        ai_result = parser.parse("브리지 살아 있어?", test_context())

        self.assertTrue(rule_result.success)
        self.assertEqual(rule_result.source, "rule")
        self.assertEqual(rule_result.first_intent.key, "weather.query")
        self.assertTrue(ai_result.success)
        self.assertEqual(ai_result.source, "ai")
        self.assertEqual(ai_result.first_intent.key, "integration_n8n.health")

    def test_planner_converts_ai_intent_to_dispatchable_step(self):
        """Runtime Planner turns AI intent into Dispatcher steps."""
        dispatcher = create_dispatcher(
            HybridIntentParser(
                ai_parser=AIIntentParser(
                    provider=MappingProvider({"브리지 살아 있어?": integration_health_payload()}),
                    enabled=True,
                )
            )
        )
        result = dispatcher.execute_plan_text("브리지 살아 있어?")

        self.assertTrue(result.success)
        self.assertIn("n8n", result.response)

    def test_voice_pipeline_executes_ai_intent_plan_before_llm_fallback(self):
        """Voice runtime executes AI-created plans instead of falling back to chat."""
        dispatcher = create_dispatcher(
            HybridIntentParser(
                ai_parser=AIIntentParser(
                    provider=StaticProvider(integration_health_payload()),
                    enabled=True,
                )
            )
        )
        pipeline = VoicePipeline(
            wake_listener=None,
            stt_provider=None,
            chat_service=CapturingChatService(),
            tts_provider=None,
            intent_runtime=IntentRuntime(tool_dispatcher=dispatcher),
        )

        result = pipeline.try_intent_runtime("브릿지 살아 있어?")

        self.assertTrue(result.handled)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "integration_n8n")
        self.assertIn("n8n", result.response)
        self.assertEqual(pipeline.chat_service.messages, [])

    def test_planner_can_force_ai_intent_before_rule_routing(self):
        """Manual test mode can force AI Intent Parser before rule planning."""
        previous = os.environ.get("JARVIS_AI_INTENT_FORCE")
        os.environ["JARVIS_AI_INTENT_FORCE"] = "true"
        try:
            dispatcher = create_dispatcher(
                HybridIntentParser(
                    ai_parser=AIIntentParser(
                        provider=StaticProvider(integration_health_payload()),
                        enabled=True,
                    )
                )
            )
            plan = dispatcher.create_plan("외부 자동화 상태 좀 봐 줘")
        finally:
            restore_env("JARVIS_AI_INTENT_FORCE", previous)

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "integration_n8n")
        self.assertEqual(plan.steps[0].action, "health")

    def test_planner_labels_rule_integration_health_action(self):
        """Rule-routed integration health steps show health in planner traces."""
        dispatcher = create_dispatcher(None)
        plan = dispatcher.create_plan("외부 자동화 상태로 봐 줄래")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "integration_n8n")
        self.assertEqual(plan.steps[0].action, "health")

    def test_intent_metrics_collector_calculates_rates(self):
        """Intent metrics expose PM-friendly percentages and confidence."""
        metrics = IntentMetricsCollector()

        metrics.record("rule", confidence=0.95)
        metrics.record("ai", confidence=0.85)
        metrics.record("fallback", confidence=0.40)
        metrics.record("ai", confidence=0.80, requires_clarification=True)

        snapshot = metrics.snapshot()

        self.assertEqual(snapshot.total, 4)
        self.assertEqual(snapshot.rule_hit_rate, 25.0)
        self.assertEqual(snapshot.ai_hit_rate, 50.0)
        self.assertEqual(snapshot.fallback_rate, 25.0)
        self.assertEqual(snapshot.clarification_rate, 25.0)
        self.assertAlmostEqual(snapshot.average_confidence, 0.75)

    def test_hybrid_parser_records_intent_metrics(self):
        """Hybrid parser records rule, AI, fallback, and clarification selections."""
        metrics = get_intent_metrics()
        metrics.reset()

        ai_provider = MappingProvider({"브리지 살아 있어?": integration_health_payload()})
        HybridIntentParser(ai_parser=AIIntentParser(provider=ai_provider, enabled=True)).parse(
            "오늘 강릉 날씨 알려줘",
            test_context(),
        )
        HybridIntentParser(ai_parser=AIIntentParser(provider=ai_provider, enabled=True)).parse(
            "브리지 살아 있어?",
            test_context(),
        )
        HybridIntentParser(ai_parser=AIIntentParser(provider=FailingProvider(), enabled=True)).parse(
            "unknown input",
            test_context(),
        )
        HybridIntentParser(
            ai_parser=AIIntentParser(
                provider=StaticProvider(
                    {
                        "intents": [
                            {
                                "intent_id": "calendar.create",
                                "ability": "calendar",
                                "action": "create",
                                "parameters": {"date": "2026-07-14", "time": "15:00", "title": "?뚯쓽"},
                                "confidence": 0.78,
                            }
                        ]
                    }
                ),
                enabled=True,
            )
        ).parse("애매한 일정", test_context())

        snapshot = metrics.snapshot()
        metrics.reset()

        self.assertEqual(snapshot.total, 4)
        self.assertEqual(snapshot.rule_hits, 1)
        self.assertEqual(snapshot.ai_hits, 2)
        self.assertEqual(snapshot.fallback_hits, 1)
        self.assertEqual(snapshot.clarification_hits, 1)
        self.assertEqual(snapshot.rule_hit_rate, 25.0)
        self.assertEqual(snapshot.ai_hit_rate, 50.0)
        self.assertEqual(snapshot.fallback_rate, 25.0)
        self.assertEqual(snapshot.clarification_rate, 25.0)

    def test_planner_returns_clarification_response(self):
        """Clarification intent becomes a runtime response, not execution."""
        dispatcher = create_dispatcher(
            HybridIntentParser(
                ai_parser=AIIntentParser(
                    provider=StaticProvider(
                        {
                            "requires_clarification": True,
                            "clarification_question": "내일 몇 시에 등록할까요?",
                            "intents": [],
                        }
                    ),
                    enabled=True,
                )
            )
        )
        result = dispatcher.execute_plan_text("내일 일정 등록해줘")

        self.assertFalse(result.success)
        self.assertEqual(result.error, "requires_clarification")
        self.assertEqual(result.response, "내일 몇 시에 등록할까요?")


def integration_health_payload():
    return {
        "intents": [
            {
                "intent_id": "integration.health",
                "ability": "integration_n8n",
                "action": "health",
                "entities": {"workflow_key": "system.health"},
                "parameters": {},
                "confidence": 0.94,
            }
        ]
    }


def integration_execute_payload(workflow_key, message):
    return {
        "intents": [
            {
                "intent_id": "integration.execute",
                "ability": "integration_n8n",
                "action": "execute",
                "parameters": {"workflow_key": workflow_key, "message": message},
                "confidence": 0.94,
            }
        ]
    }


def calendar_create_payload(title="아야 만나기"):
    return {
        "intents": [
            {
                "intent_id": "calendar.create",
                "ability": "calendar",
                "action": "create",
                "parameters": {"date": "2026-07-14", "time": "15:00", "title": title},
                "confidence": 0.94,
            }
        ]
    }


def reminder_create_payload(relative_minutes=1):
    return {
        "intents": [
            {
                "intent_id": "reminder.create",
                "ability": "reminder",
                "action": "create",
                "parameters": {"relative_minutes": relative_minutes, "title": "물 마시기"},
                "confidence": 0.94,
            }
        ]
    }


def memory_remember_payload():
    return {
        "intents": [
            {
                "intent_id": "memory.remember",
                "ability": "memory",
                "action": "remember",
                "parameters": {
                    "key": "relationship.aya.birthday",
                    "value": "1991-02-28",
                    "category": "relationship",
                    "scope": "long_term",
                },
                "confidence": 0.94,
            }
        ]
    }


def test_context():
    return IntentContext(
        session_id="test-session",
        current_date="2026-07-13",
        current_time="12:00:00",
        timezone="Asia/Seoul",
        available_abilities=("weather", "memory", "calendar", "reminder", "integration_n8n"),
        user_vocabulary={"아야": ["아이와"], "유이": [], "유리": []},
    )


def create_dispatcher(intent_parser):
    tool_registry = ToolRegistry()
    ability_registry = AbilityRegistry()
    ability_registry.register(WeatherAbility())
    ability_registry.register(MemoryAbility())
    ability_registry.register(CalendarAbility())
    ability_registry.register(ReminderAbility())
    ability_registry.register(N8nIntegrationAbility(bridge=MockIntegrationBridge()))
    ability_registry.register_tools(tool_registry)
    return RuntimeToolDispatcher(tool_registry, intent_parser=intent_parser)


class StaticProvider:
    """Fake LLM provider that returns one JSON payload."""

    def __init__(self, payload):
        self.payload = payload
        self.last_metadata = None

    def generate(self, prompt):
        return json.dumps(self.payload, ensure_ascii=False)

    def metadata(self):
        return ProviderMetadata()


class MappingProvider(StaticProvider):
    """Fake LLM provider keyed by input text in the JSON prompt."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.last_metadata = None

    def generate(self, prompt):
        request = json.loads(prompt)
        return json.dumps(self.mapping[request["text"]], ensure_ascii=False)


class FailingProvider(StaticProvider):
    """Fake provider that raises an error."""

    def __init__(self):
        self.last_metadata = None

    def generate(self, prompt):
        raise RuntimeError("provider failed")


class ProviderMetadata:
    """Small provider metadata stub."""

    model = "fake-intent-model"


class ProviderUsage:
    """Small provider token usage stub."""

    input_tokens = 12
    output_tokens = 34


class CapturingProviderMetadata:
    """Small provider metadata stub with finish reason and usage."""

    def __init__(self, finish_reason="stop"):
        self.model = "fake-intent-model"
        self.finish_reason = finish_reason
        self.usage = ProviderUsage()


class CapturingIntentProvider:
    """Fake LLM provider that records prompt and generation options."""

    def __init__(self, payload, finish_reason="stop"):
        self.payload = payload
        self.prompt = ""
        self.options = {}
        self.last_metadata = CapturingProviderMetadata(finish_reason=finish_reason)

    def generate(self, prompt, **options):
        self.prompt = prompt
        self.options = options
        return json.dumps(self.payload, ensure_ascii=False)

    def metadata(self):
        return self.last_metadata


class CapturingChatService:
    """Chat service test double that must not be called for handled intents."""

    provider = object()

    def __init__(self):
        self.messages = []

    def generate_reply(self, message):
        self.messages.append(message)
        return f"reply: {message}"


def restore_env(key, previous):
    """Restore an environment variable to its previous state."""
    if previous is None:
        os.environ.pop(key, None)
        return

    os.environ[key] = previous


if __name__ == "__main__":
    unittest.main()
