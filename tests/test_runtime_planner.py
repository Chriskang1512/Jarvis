import io
import os
import unittest
from datetime import date, timedelta
from contextlib import redirect_stdout
from unittest.mock import patch

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.calendar import CalendarAbility, MockCalendarProvider
from jarvis.abilities.native.memory import InMemoryStorage, MemoryAbility
from jarvis.abilities.native.reminder import ReminderAbility
from jarvis.abilities.native.weather import MockWeatherProvider, WeatherAbility
from jarvis.native.reminder import ReminderEngine, ReminderQueue
from jarvis.runtime.planner import RuntimePlanner
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.tools import ToolRegistry


class TestRuntimePlannerSprint6(unittest.TestCase):
    """Test Runtime Planner and multi-tool execution."""

    def test_planner_creates_calendar_then_reminder_plan(self):
        """Check one sentence can become Calendar.create -> Reminder.create."""
        planner = RuntimePlanner()
        plan = planner.plan(
            "\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \uc544\uc57c \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud558\uace0 30\ubd84 \uc804\uc5d0 \uc54c\ub824\uc918",
            create_sprint6_registry()[0],
        )

        self.assertEqual([step.tool_name for step in plan.steps], ["calendar", "reminder"])
        self.assertEqual([step.action for step in plan.steps], ["create", "create"])
        self.assertEqual(plan.steps[1].depends_on, (1,))
        self.assertEqual(plan.steps[1].input_data["remind_before"], 30)
        self.assertEqual(plan.steps[0].input_data["remind_before_minutes"], 30)

    def test_planner_copies_korean_word_hour_reminder_override_to_calendar_step(self):
        """Check spoken 'one hour before' Korean phrasing is not treated as ambiguous."""
        planner = RuntimePlanner()
        plan = planner.plan(
            "\u0038\uc6d4 \u0031\u0034\uc77c \uc624\ud6c4 \u0032\uc2dc\uc5d0 \uc544\uc57c \ub9cc\ub098\uae30 \uc77c\uc815 \uc7a1\uace0 \ud55c \uc2dc\uac04 \uc804\uc5d0 \uc54c\ub824 \uc918",
            create_sprint6_registry()[0],
        )

        self.assertEqual([step.tool_name for step in plan.steps], ["calendar", "reminder"])
        self.assertEqual([step.action for step in plan.steps], ["create", "create"])
        self.assertFalse(plan.requires_clarification)
        self.assertEqual(plan.steps[0].input_data["remind_before_minutes"], 60)
        self.assertEqual(plan.steps[1].input_data["remind_before"], 60)

    def test_planner_routes_meeting_alarm_registration_to_calendar(self):
        """Check STT saying 'alarm registration' does not steal meeting calendar intent."""
        planner = RuntimePlanner()
        plan = planner.plan(
            "\ub0b4\uc77c \uc624\ud6c4 \u0032\uc2dc\uc5d0 \uce5c\uad6c \ub9cc\ub098\uae30 \uc54c\ub78c \ub4f1\ub85d\ud558\uace0 \ud55c \uc2dc\uac04 \uc804\uc5d0 \uc54c\ub824 \uc918",
            create_sprint6_registry()[0],
        )

        self.assertEqual([step.tool_name for step in plan.steps], ["calendar", "reminder"])
        self.assertEqual([step.action for step in plan.steps], ["create", "create"])
        self.assertEqual(plan.steps[0].input_data["remind_before_minutes"], 60)
        self.assertEqual(plan.steps[1].input_data["remind_before"], 60)

    def test_planner_routes_meeting_alarm_insert_to_calendar(self):
        """Check STT saying 'add alarm too' still means calendar create with a reminder."""
        planner = RuntimePlanner()
        plan = planner.plan(
            "내일 오후 2시에 친구 만나기 알람도 넣고 한 시간 전 알려줘.",
            create_sprint6_registry()[0],
        )

        self.assertEqual([step.tool_name for step in plan.steps], ["calendar", "reminder"])
        self.assertEqual([step.action for step in plan.steps], ["create", "create"])
        self.assertEqual(plan.steps[0].input_data["remind_before_minutes"], 60)
        self.assertEqual(plan.steps[1].input_data["remind_before"], 60)
        self.assertIn("일정", plan.steps[0].raw_text)
        self.assertNotIn("줘", str(plan.steps[0].input_data.get("title", "")))

    def test_planner_treats_relative_notice_as_calendar_reminder_modifier(self):
        """Check event plus relative notice does not route as standalone Reminder."""
        planner = RuntimePlanner()
        plan = planner.plan(
            "내일 오후 2시에 친구 만나기 한 시간 전 알려줘.",
            create_sprint6_registry()[0],
        )

        self.assertEqual([step.tool_name for step in plan.steps], ["calendar", "reminder"])
        self.assertEqual(plan.steps[0].input_data["remind_before_minutes"], 60)
        self.assertEqual(plan.steps[1].input_data["remind_before"], 60)

    def test_planner_copies_hour_reminder_override_to_calendar_step(self):
        """Check Google Calendar create can receive the user reminder override."""
        planner = RuntimePlanner()
        plan = planner.plan(
            "내일 오후 3시에 우수 만나기 일정 잡고 1시간 전에 알려줘",
            create_sprint6_registry()[0],
        )

        self.assertEqual([step.tool_name for step in plan.steps], ["calendar", "reminder"])
        self.assertEqual(plan.steps[0].input_data["remind_before_minutes"], 60)
        self.assertEqual(plan.steps[1].input_data["remind_before"], 60)

    def test_planner_splits_spoken_calendar_reminder_before_ai(self):
        """Check spoken '잡고 30분 전 알려 줘' is handled by rules first."""

        class FailingIntentParser:
            def parse(self, text, context):
                raise AssertionError("AI intent parser should not run for this rule-safe phrase.")

        planner = RuntimePlanner(intent_parser=FailingIntentParser())
        plan = planner.plan(
            "\ub0b4\uc77c 3\uc2dc\uc5d0 \uc57d\uc18d \uc7a1\uace0 30\ubd84 \uc804 \uc54c\ub824 \uc918",
            create_sprint6_registry()[0],
        )

        self.assertEqual([step.tool_name for step in plan.steps], ["calendar", "reminder"])
        self.assertEqual([step.action for step in plan.steps], ["create", "create"])
        self.assertEqual(plan.steps[0].raw_text, "\ub0b4\uc77c 3\uc2dc\uc5d0 \uc57d\uc18d \uc7a1\uc544 \uc918")
        self.assertEqual(plan.steps[1].input_data["remind_before"], 30)

    def test_planner_does_not_create_reminder_from_plain_tell_me(self):
        """Check plain tell-me wording without time is not standalone Reminder create."""
        planner = RuntimePlanner()
        plan = planner.plan("택배일 알려줘", create_sprint6_registry()[0])

        self.assertFalse(any(step.tool_name == "reminder" and step.action == "create" for step in plan.steps))

    def test_dispatcher_executes_calendar_then_reminder_plan(self):
        """Check Dispatcher executes planned steps and merges responses."""
        registry, reminder_engine, calendar_provider = create_sprint6_registry()
        dispatcher = RuntimeToolDispatcher(registry)

        result = dispatcher.execute_plan_text(
            "\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \uc544\uc57c \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud558\uace0 30\ubd84 \uc804\uc5d0 \uc54c\ub824\uc918",
            confirmed=True,
        )

        self.assertTrue(result.success)
        self.assertEqual([item.tool_name for item in result.step_results], ["calendar", "reminder"])
        self.assertEqual(result.response, "\uc77c\uc815\uc744 \ub4f1\ub85d\ud588\uace0, 30\ubd84 \uc804 \uc54c\ub9bc\ub3c4 \ub4f1\ub85d\ud588\uc2b5\ub2c8\ub2e4.")
        self.assertEqual(len(calendar_provider.events), 1)
        self.assertEqual(len(reminder_engine.list(state="pending")), 1)
        expected_trigger = f"{date.today() + timedelta(days=1)}T14:30:00"
        self.assertEqual(reminder_engine.list(state="pending")[0].trigger_time, expected_trigger)

    def test_dispatcher_executes_spoken_calendar_reminder_plan(self):
        """Check the live voice phrase creates the event and attached reminder."""
        registry, reminder_engine, calendar_provider = create_sprint6_registry()
        dispatcher = RuntimeToolDispatcher(registry)

        result = dispatcher.execute_plan_text(
            "\ub0b4\uc77c 3\uc2dc\uc5d0 \uc57d\uc18d \uc7a1\uace0 30\ubd84 \uc804 \uc54c\ub824 \uc918",
            confirmed=True,
        )

        self.assertTrue(result.success)
        self.assertEqual([item.tool_name for item in result.step_results], ["calendar", "reminder"])
        self.assertEqual(calendar_provider.events[0].title, "\uc57d\uc18d")
        self.assertEqual(len(reminder_engine.list(state="pending")), 1)
        expected_trigger = f"{date.today() + timedelta(days=1)}T14:30:00"
        self.assertEqual(reminder_engine.list(state="pending")[0].trigger_time, expected_trigger)

    def test_planner_routes_single_calendar_registration_to_calendar(self):
        """Check a plain calendar registration is not misrouted as a reminder."""
        planner = RuntimePlanner()
        plan = planner.plan(
            "\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \uc544\uc57c \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud574",
            create_sprint6_registry()[0],
        )

        self.assertEqual([step.tool_name for step in plan.steps], ["calendar"])
        self.assertEqual([step.action for step in plan.steps], ["create"])

    def test_dispatcher_traces_each_multi_tool_step_execution(self):
        """Check logs distinguish planner step execution from calendar auto-reminders."""
        registry, _, _ = create_sprint6_registry()
        dispatcher = RuntimeToolDispatcher(registry)
        output = io.StringIO()

        with patch.dict(os.environ, {"JARVIS_DEBUG_TRACE": "true", "JARVIS_TRACE_RAW": ""}, clear=False):
            with redirect_stdout(output):
                dispatcher.execute_plan_text(
                    "\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \uc544\uc57c \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud558\uace0 30\ubd84 \uc804\uc5d0 \uc54c\ub824\uc918",
                    confirmed=True,
                )

        trace_output = output.getvalue()

        self.assertIn("[Planner] resume_after_confirmation", trace_output)
        self.assertIn("[Planner] executing step=1/2 calendar.create", trace_output)
        self.assertIn("[Planner] executing step=2/2 reminder.create", trace_output)
        self.assertIn("[Planner] completed steps=2", trace_output)

    def test_planner_creates_memory_then_calendar_plan(self):
        """Check mixed Memory and Calendar clauses are ordered."""
        planner = RuntimePlanner()
        plan = planner.plan(
            "\uc544\uc57c \uc0dd\uc77c \uae30\uc5b5\ud574 \uadf8\ub9ac\uace0 \ub0b4\uc77c \uc77c\uc815 \ub4f1\ub85d\ud574",
            create_sprint6_registry()[0],
        )

        self.assertEqual([step.tool_name for step in plan.steps], ["memory", "calendar"])

    def test_planner_marks_weather_reminder_condition_unsupported(self):
        """Check conditional weather reminder text is not half-executed."""
        planner = RuntimePlanner()
        plan = planner.plan(
            "\ub0b4\uc77c \ube44 \uc624\uba74 \uc6b0\uc0b0 \ucc59\uae30\ub77c\uace0 \uc54c\ub824\uc918",
            create_sprint6_registry()[0],
        )

        self.assertEqual(plan.unsupported_reason, "unsupported_conditional")
        self.assertEqual(len(plan.steps), 0)

    def test_planner_routes_current_rain_question_to_weather(self):
        """Check current rain questions do not fall into datetime validation failure."""
        planner = RuntimePlanner()
        registry = create_sprint6_registry()[0]

        plan = planner.plan("강릉 지금 비와?", registry)

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "weather")
        self.assertEqual(plan.steps[0].action, "query")

    def test_dispatcher_returns_safe_response_for_unsupported_conditional(self):
        """Check unsupported conditionals return a safe response."""
        registry, _, _ = create_sprint6_registry()
        dispatcher = RuntimeToolDispatcher(registry)

        result = dispatcher.execute_plan_text("\ub0b4\uc77c \ube44 \uc624\uba74 \uc6b0\uc0b0 \ucc59\uae30\ub77c\uace0 \uc54c\ub824\uc918")

        self.assertFalse(result.success)
        self.assertEqual(result.error, "unsupported_conditional")
        self.assertEqual(result.response, "\uc544\uc9c1 \uc870\uac74\ubd80 \uc54c\ub9bc\uc740 \uc9c0\uc6d0\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.")

    def test_ambiguous_reminder_does_not_fall_through_to_llm(self):
        """Check vague reminder requests ask for time instead of fake success."""
        planner = RuntimePlanner()
        plan = planner.plan("\uc870\uae08 \uc788\ub2e4\uac00 \ubb3c \ub9c8\uc2dc\ub77c\uace0 \ucc59\uaca8 \uc918", create_sprint6_registry()[0])

        self.assertTrue(plan.requires_clarification)
        self.assertEqual(plan.clarification_question, "\uba87 \ubd84 \ub4a4\uc5d0 \uc54c\ub824\ub4dc\ub9b4\uae4c\uc694?")
        self.assertEqual(plan.step_count, 0)

    def test_seconds_reminder_is_blocked_until_supported(self):
        """Check seconds-based reminder requests are not mis-scheduled."""
        planner = RuntimePlanner()
        plan = planner.plan("30\ucd08 \ud6c4\uc5d0 \uc54c\ub824 \uc918", create_sprint6_registry()[0])

        self.assertTrue(plan.requires_clarification)
        self.assertIn("\ucd08 \ub2e8\uc704", plan.clarification_question)
        self.assertEqual(plan.step_count, 0)

    def test_single_intent_regressions_stay_single_step(self):
        """Check common single requests still produce one planned step."""
        planner = RuntimePlanner()
        registry = create_sprint6_registry()[0]
        cases = [
            ("\uc624\ub298 \ub0a0\uc528", "weather"),
            ("\uc624\ub298 \uc77c\uc815", "calendar"),
            ("\uba54\ubaa8 \uae30\uc5b5\ud574", "memory"),
            ("\u0031\ubd84 \ub4a4 \ubb3c \ub9c8\uc2dc\uae30 \uc54c\ub824\uc918", "reminder"),
        ]

        for text, tool_name in cases:
            with self.subTest(text=text):
                plan = planner.plan(text, registry)

                self.assertEqual(len(plan.steps), 1)
                self.assertEqual(plan.steps[0].tool_name, tool_name)

    def test_calendar_appointment_trace_action_is_create_for_spoken_promise(self):
        """Check spoken promise creation is traced as Calendar.create."""
        planner = RuntimePlanner()
        plan = planner.plan("내일 3시쯤에 아이 만나기로 약속 잡아 줘", create_sprint6_registry()[0])

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_name, "calendar")
        self.assertEqual(plan.steps[0].action, "create")

    def test_calendar_title_cleanup_removes_follow_up_fragments(self):
        """Check Calendar title does not absorb later reminder or memory clauses."""
        from jarvis.abilities.native.calendar.parser import parse_calendar_intent

        first = parse_calendar_intent(
            "\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \uc544\uc57c \uc720\uc774 \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud558\uace0 30\ubd84 \uc804\uc5d0 \uc54c\ub824 \uc918"
        )
        second = parse_calendar_intent(
            "\ub0b4 \uc0dd\uc77c\uc740 6\uc6d4 29\uc77c \uae30\uc5b5\ud574 \uadf8\ub9ac\uace0 \ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \uc77c\uc815 \ub4f1\ub85d\ud574"
        )

        self.assertEqual(first.title, "\uc544\uc57c \uc720\uc774 \ub9cc\ub098\uae30")
        self.assertNotIn("\uadf8\ub9ac\uace0", second.title)
        self.assertNotIn("\uae30\uc5b5", second.title)

    def test_user_vocabulary_cleans_meeting_aliases(self):
        """Check STT aliases for names and meeting words are canonicalized."""
        from jarvis.voice.user_vocabulary import normalize_stt_text

        result = normalize_stt_text("\uc544\uc608 \uc720\uc774 \ub9c8\ub098\ub9ac")

        self.assertEqual(result.normalized_text, "\uc544\uc57c \uc720\uc774 \ub9cc\ub098\uae30")


def create_sprint6_registry():
    """Create registry with shared Calendar and Reminder objects."""
    tool_registry = ToolRegistry()
    ability_registry = AbilityRegistry()
    calendar_provider = MockCalendarProvider(events=[])
    reminder_engine = ReminderEngine(queue=ReminderQueue())
    ability_registry.register(WeatherAbility(provider=MockWeatherProvider()))
    ability_registry.register(CalendarAbility(provider=calendar_provider))
    ability_registry.register(MemoryAbility(storage=InMemoryStorage()))
    ability_registry.register(ReminderAbility(engine=reminder_engine))
    ability_registry.register_tools(tool_registry)
    return tool_registry, reminder_engine, calendar_provider


if __name__ == "__main__":
    unittest.main()
