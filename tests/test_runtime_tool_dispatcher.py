import unittest

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.calendar import CalendarAbility, MockCalendarProvider
from jarvis.abilities.native.memory import InMemoryStorage, MemoryAbility
from jarvis.abilities.native.reminder import ReminderAbility
from jarvis.abilities.native.weather import MockWeatherProvider, WeatherAbility
from jarvis.brain import IntentRuntime
from jarvis.native.reminder import ReminderEngine, ReminderQueue
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher, RuntimeToolRegistry
from jarvis.tools import ToolRegistry


class TestRuntimeToolDispatcherSprint5(unittest.TestCase):
    """Test Sprint 5 Runtime Tool Dispatcher foundation."""

    def test_dispatcher_registry_orders_by_priority(self):
        """Check registry facade sorts priority high before normal."""
        registry = create_sprint5_registry()
        registry.get("weather").metadata.priority = 100
        registry.get("calendar").metadata.priority = 0

        ordered = RuntimeToolRegistry(registry).list()

        self.assertEqual(ordered[0].metadata.name, "weather")

    def test_ability_metadata_has_common_fields(self):
        """Check Ability metadata exposes common dispatcher fields."""
        registry = create_sprint5_registry()
        weather = registry.get("weather").metadata

        self.assertEqual(weather.name, "weather")
        self.assertEqual(weather.version, "1.0")
        self.assertEqual(weather.provider, "mock")
        self.assertEqual(weather.priority_label, "normal")
        self.assertIn("ability.weather", weather.capability)

    def test_dispatcher_selects_weather_calendar_memory(self):
        """Check dispatcher selection for core native abilities."""
        dispatcher = RuntimeToolDispatcher(create_sprint5_registry())

        self.assertEqual(dispatcher.select("오늘 강릉 날씨 알려줘").tool_name, "weather")
        self.assertEqual(dispatcher.select("내일 일정 알려줘").tool_name, "calendar")
        self.assertEqual(dispatcher.select("내 이름은 크리스야 기억해").tool_name, "memory")
        self.assertEqual(
            dispatcher.select("\u0031\ubd84 \ub4a4\uc5d0 \ubb3c \ub9c8\uc2dc\uac8c \uc54c\ub78c \ub4f1\ub85d\ud574").tool_name,
            "reminder",
        )

    def test_dispatcher_execute_text_runs_selected_weather(self):
        """Check free-text selection executes a selected ability."""
        dispatcher = RuntimeToolDispatcher(create_sprint5_registry())

        result = dispatcher.execute_text("오늘 강릉 날씨 알려줘")

        self.assertTrue(result.success)
        self.assertEqual(result.selected.tool_name, "weather")
        self.assertEqual(result.tool_result.tool_name, "weather")

    def test_dispatcher_execute_text_runs_direct_reminder_alarm(self):
        """Check direct alarm language creates a real Reminder entry."""
        dispatcher = RuntimeToolDispatcher(create_sprint5_registry())

        result = dispatcher.execute_text("\u0031\ubd84 \ub4a4\uc5d0 \ubb3c \ub9c8\uc2dc\uac8c \uc54c\ub78c \ub4f1\ub85d\ud574")

        self.assertTrue(result.success)
        self.assertEqual(result.selected.tool_name, "reminder")
        self.assertEqual(result.tool_result.tool_name, "reminder")

    def test_dispatcher_routes_relative_tell_me_reminder_patterns(self):
        """Check relative tell-me phrases route to Reminder without alarm noun."""
        dispatcher = RuntimeToolDispatcher(create_sprint5_registry())
        texts = [
            "\u0031\ubd84 \ub4a4\uc5d0 \ubb3c \ub9c8\uc2dc\ub77c\uace0 \uc54c\ub824 \uc918",
            "\u0031\ubd84 \ub4a4 \ubb3c \ub9c8\uc2dc\ub77c\uace0 \uc54c\ub824 \uc918",
            "\u0031\ubd84 \ub4a4\uc5d0 \ubb3c \ub9c8\uc2dc\ub77c\uace0 \uc54c\ub9bc",
            "\u0031\ubd84 \ub4a4\uc5d0 \ubb3c \ub9c8\uc2dc\ub77c\uace0 \ud574 \uc918",
        ]

        for text in texts:
            with self.subTest(text=text):
                result = dispatcher.execute_text(text)

                self.assertTrue(result.success)
                self.assertEqual(result.selected.tool_name, "reminder")
                self.assertEqual(result.tool_result.tool_name, "reminder")

    def test_dispatcher_multi_tool_plan_is_ready_without_execution(self):
        """Check multi-tool request prepares multiple selections."""
        dispatcher = RuntimeToolDispatcher(create_sprint5_registry())

        result = dispatcher.plan("오늘 일정 알려주고 오늘 강릉 날씨 알려줘")

        self.assertTrue(result.success)
        self.assertTrue(result.multi_tool_ready)
        self.assertEqual([selection.tool_name for selection in result.selections], ["calendar", "weather"])

    def test_intent_runtime_uses_runtime_tool_dispatcher(self):
        """Check existing IntentRuntime can use only the new dispatcher facade."""
        dispatcher = RuntimeToolDispatcher(create_sprint5_registry())
        runtime = IntentRuntime(tool_dispatcher=dispatcher)

        result = runtime.run("오늘 강릉 날씨 알려줘", input_source="voice")

        self.assertTrue(result.handled)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "weather")


def create_sprint5_registry():
    """Create a deterministic native ability registry."""
    tool_registry = ToolRegistry()
    ability_registry = AbilityRegistry()
    ability_registry.register(WeatherAbility(provider=MockWeatherProvider()))
    ability_registry.register(CalendarAbility(provider=MockCalendarProvider()))
    ability_registry.register(MemoryAbility(storage=InMemoryStorage()))
    ability_registry.register(ReminderAbility(engine=ReminderEngine(queue=ReminderQueue())))
    ability_registry.register_tools(tool_registry)
    return tool_registry


if __name__ == "__main__":
    unittest.main()
