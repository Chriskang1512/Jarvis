import io
import os
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from unittest.mock import patch

from jarvis.abilities import AbilityHealth, AbilityRegistry, AbilityResult, AbilityToolAdapter, AbilityType
from jarvis.abilities.native.calendar import CalendarAbility, CalendarIntentParser, CalendarResult
from jarvis.abilities.native.calendar import CalendarEvent
from jarvis.abilities.native.calendar import MockCalendarProvider, GoogleCalendarProvider
from jarvis.abilities.native.memory import JsonMemoryStorage, MemoryAbility, MemoryEntry, MemoryIntentParser, MemoryResult
from jarvis.abilities.native.weather import MockWeatherProvider, WeatherAbility, WeatherResult
from jarvis.abilities.native.weather import WeatherIntentParser
from jarvis.abilities.native.weather import WeatherQuery
from jarvis.abilities.native.weather import WeatherLocationResolver
from jarvis.abilities.native.weather.provider import OpenWeatherProvider
from jarvis.abilities.native.weather.provider import FallbackWeatherProvider
from jarvis.abilities.native.weather.provider import create_weather_provider, normalize_openweather_response
from jarvis.brain import BrainToolRouter, IntentRuntime
from jarvis.commands.chat import ChatCommand
from jarvis.config.loader import create_config_from_dict
from jarvis.config.settings import WeatherConfig
from jarvis.permissions import PermissionLevel
from jarvis.providers.google.config import GoogleProviderConfig
from jarvis.tools import ToolDispatcher, ToolRequest
from jarvis.tools.registry import ToolRegistry, create_default_tool_registry


class TestAbilities(unittest.TestCase):
    """Test the v0.6 Ability contract and ToolRouter adapter."""

    def test_calendar_metadata_contains_required_manifest_fields(self):
        """Check Calendar exposes the Ability manifest."""
        metadata = CalendarAbility().metadata

        self.assertEqual(metadata.id, "calendar")
        self.assertEqual(metadata.name, "Calendar")
        self.assertEqual(metadata.type, AbilityType.NATIVE)
        self.assertEqual(metadata.permission, PermissionLevel.SAFE)
        self.assertEqual(metadata.output_schema, "CalendarResult")
        self.assertIn("calendar", metadata.capabilities)
        self.assertIn("schedule", metadata.capabilities)
        self.assertIn("appointment", metadata.capabilities)

    def test_calendar_parser_list_today_tomorrow_and_week(self):
        """Check Calendar parser understands list date scopes."""
        today_query = CalendarIntentParser().parse("오늘 일정 알려줘")
        tomorrow_query = CalendarIntentParser().parse("내일 일정 알려줘")
        week_query = CalendarIntentParser().parse("이번주 일정 알려줘")

        self.assertEqual(today_query.action, "list")
        self.assertEqual(tomorrow_query.action, "list")
        self.assertEqual(week_query.action, "list")
        self.assertEqual(week_query.date, "week")

        next_week_query = CalendarIntentParser().parse("\ub2e4\uc74c \uc8fc \uc77c\uc815 \uc54c\ub824\uc918")
        next_query = CalendarIntentParser().parse("\ub2e4\uc74c \uc77c\uc815 \uc54c\ub824\uc918")

        self.assertEqual(next_week_query.action, "list")
        self.assertEqual(next_week_query.date, "next_week")
        self.assertEqual(next_query.action, "list")
        self.assertEqual(next_query.date, "next")

    def test_calendar_parser_create_appointment(self):
        """Check Calendar parser extracts create appointment fields."""
        query = CalendarIntentParser().parse("내일 오후 3시에 치과 예약해")

        self.assertEqual(query.action, "create")
        self.assertEqual(query.time, "15:00")
        self.assertEqual(query.title, "치과")

    def test_calendar_parser_create_appointment_with_spoken_time_words(self):
        """Check Calendar parser handles OpenAI STT spoken time words."""
        query = CalendarIntentParser().parse("내일 오후 세 시에 혜와 만나기 일정 등록해")

        self.assertEqual(query.action, "create")
        self.assertEqual(query.time, "15:00")
        self.assertEqual(query.title, "아야 만나기")
        self.assertEqual(query.participants, ["아야"])

    def test_calendar_parser_cleans_casual_meeting_phrase(self):
        """Check casual spoken meeting text becomes a clean PM appointment."""
        query = CalendarIntentParser().parse("내일 3시쯤에 아이 만나기로 약속 잡아 줘")

        self.assertEqual(query.action, "create")
        self.assertEqual(query.time, "15:00")
        self.assertEqual(query.title, "아야 만나기")
        self.assertEqual(query.participants, ["아야"])

    def test_calendar_parser_keeps_generic_promise_title(self):
        """Check bare promise commands keep promise as the title."""
        query = CalendarIntentParser().parse("내일 3시에 약속 잡아 줘")

        self.assertEqual(query.action, "create")
        self.assertEqual(query.time, "15:00")
        self.assertEqual(query.title, "약속")

    def test_calendar_mock_provider_lists_events(self):
        """Check MockCalendarProvider returns deterministic events."""
        result = CalendarAbility(provider=MockCalendarProvider()).execute({"text": "오늘 일정 알려줘"})

        self.assertTrue(result.success)
        self.assertIsInstance(result.data, CalendarResult)
        self.assertEqual(result.data.provider, "mock")
        self.assertEqual(result.data.count, 2)
        self.assertIn("오늘 일정은 2건입니다", result.data.to_natural_language())

    def test_calendar_list_response_uses_query_date_label(self):
        """Check tomorrow list results say tomorrow, not today."""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        provider = MockCalendarProvider(
            events=[CalendarEvent(id="mock-tomorrow", title="meeting", date=tomorrow, time="15:00")]
        )

        result = CalendarAbility(provider=provider).execute({"date": tomorrow, "action": "list"})

        self.assertTrue(result.success)
        self.assertIn("\ub0b4\uc77c \uc77c\uc815\uc740 1\uac74\uc785\ub2c8\ub2e4", result.data.to_natural_language())
        self.assertIn("1. \ub0b4\uc77c \uc624\ud6c4 3\uc2dc meeting", result.data.to_natural_language())

    def test_calendar_polish_filters_afternoon_and_first_event(self):
        """Check coarse time and position hints polish list output."""
        today_value = date.today().isoformat()
        provider = MockCalendarProvider(
            events=[
                CalendarEvent(id="morning", title="\uc544\uce68 \ud68c\uc758", date=today_value, time="09:00"),
                CalendarEvent(id="afternoon", title="\uc624\ud6c4 \ud68c\uc758", date=today_value, time="15:00"),
                CalendarEvent(id="evening", title="\uc800\ub141 \ud68c\uc758", date=today_value, time="19:00"),
            ]
        )
        ability = CalendarAbility(provider=provider)

        afternoon = ability.execute({"text": "\uc624\ud6c4 \uc77c\uc815 \uc54c\ub824\uc918"})
        first = ability.execute({"text": "\uc624\ub298 \uccab \uc77c\uc815 \uc54c\ub824\uc918"})

        self.assertEqual([event.id for event in afternoon.data.events], ["afternoon"])
        self.assertIn("1. \uc624\ub298 \uc624\ud6c4 3\uc2dc \uc624\ud6c4 \ud68c\uc758", afternoon.data.to_natural_language())
        self.assertEqual([event.id for event in first.data.events], ["morning"])

    def test_calendar_mutation_ambiguous_same_title_requires_clarification(self):
        """Check duplicate title mutations are not executed blindly."""
        today_value = date.today().isoformat()
        provider = MockCalendarProvider(
            events=[
                CalendarEvent(id="one", title="\ud14c\uc2a4\ud2b8", date=today_value, time="10:00"),
                CalendarEvent(id="two", title="\ud14c\uc2a4\ud2b8", date=today_value, time="15:00"),
            ]
        )
        ability = CalendarAbility(provider=provider)

        result = ability.execute(
            {
                "action": "delete",
                "date": today_value,
                "title": "\ud14c\uc2a4\ud2b8",
                "_confirmed": True,
            }
        )

        self.assertFalse(result.success)
        self.assertEqual(result.data.error_code, "AMBIGUOUS_EVENT")
        self.assertEqual(len(provider.events), 2)
        self.assertIn("\uc5b4\ub5a4 \uc77c\uc815", result.data.to_natural_language())

    def test_calendar_mutating_actions_require_confirmation(self):
        """Check create/delete/update are not automatically executed."""
        ability = CalendarAbility(provider=MockCalendarProvider())

        create_result = ability.execute({"text": "내일 오후 3시에 치과 예약해"})
        delete_result = ability.execute({"text": "치과 일정 삭제해"})
        confirmed = ability.execute(
            {
                "action": "create",
                "date": (date.today() + timedelta(days=1)).isoformat(),
                "time": "15:00",
                "title": "치과",
                "_confirmed": True,
            }
        )

        self.assertTrue(create_result.success)
        self.assertIn("확인이 필요", create_result.data.to_natural_language())
        self.assertIn("확인이 필요", delete_result.data.to_natural_language())
        self.assertEqual(confirmed.data.action, "create")
        self.assertEqual(confirmed.data.events[0].title, "치과")

    def test_calendar_delete_all_today_after_confirmation(self):
        """Check generic today delete removes matching date events after confirmation."""
        provider = MockCalendarProvider()
        ability = CalendarAbility(provider=provider)
        today_value = date.today().isoformat()

        pending = ability.execute({"text": "오늘 일정 모두 삭제"})
        confirmed = ability.execute(
            {
                "action": "delete",
                "date": today_value,
                "title": "",
                "_confirmed": True,
            }
        )

        self.assertIn("삭제할까요", pending.data.to_natural_language())
        self.assertTrue(confirmed.success)
        self.assertEqual(confirmed.data.count, 2)
        self.assertEqual(confirmed.data.to_natural_language(), "일정을 삭제했습니다.")
        self.assertEqual(provider.events, [])

    def test_calendar_delete_success_with_no_matches_does_not_ask_confirmation_again(self):
        """Check confirmed delete with no matches reports not found, not confirmation."""
        provider = MockCalendarProvider(events=[])
        ability = CalendarAbility(provider=provider)

        result = ability.execute(
            {
                "action": "delete",
                "date": date.today().isoformat(),
                "title": "",
                "_confirmed": True,
            }
        )

        self.assertTrue(result.success)
        self.assertEqual(result.data.to_natural_language(), "삭제할 일정을 찾지 못했습니다.")

    def test_calendar_update_patches_only_changed_fields_by_event_id(self):
        """Check Calendar.update patches the referenced event without replacing other fields."""
        event = CalendarEvent(
            id="event-1",
            title="\uc544\uc57c \ub9cc\ub098\uae30",
            date="2026-07-17",
            time="15:00",
            location="\ub86f\ub370\uc6d4\ub4dc",
            participants=["\uc544\uc57c"],
        )
        provider = MockCalendarProvider(events=[event])
        ability = CalendarAbility(provider=provider)

        pending = ability.execute(
            {
                "action": "update",
                "event_id": "event-1",
                "time": "16:00",
            }
        )
        confirmed = ability.execute(
            {
                "action": "update",
                "event_id": "event-1",
                "time": "16:00",
                "_confirmed": True,
            }
        )

        self.assertIn("\uc218\uc815", pending.data.to_natural_language())
        self.assertTrue(confirmed.success)
        self.assertEqual(confirmed.data.count, 1)
        self.assertEqual(provider.events[0].time, "16:00")
        self.assertEqual(provider.events[0].title, "\uc544\uc57c \ub9cc\ub098\uae30")
        self.assertEqual(provider.events[0].location, "\ub86f\ub370\uc6d4\ub4dc")
        self.assertEqual(provider.events[0].participants, ["\uc544\uc57c"])

    def test_google_calendar_provider_boundary_exists(self):
        """Check Google Calendar provider returns a safe auth error when not connected."""
        provider = GoogleCalendarProvider(
            config=GoogleProviderConfig(
                credentials_path="tmp/missing-google-token.json",
                client_secret_path="tmp/missing-client-secret.json",
            )
        )

        result = provider.list_events(CalendarIntentParser().parse("오늘 일정 알려줘"))

        self.assertFalse(result.success)
        self.assertEqual(result.provider, "google")
        self.assertEqual(result.error_code, "AUTH_REQUIRED")

    def test_calendar_routes_through_intent_runtime(self):
        """Check Calendar list routes through the AbilityRegistry path."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=MockCalendarProvider()))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))

        result = runtime.run("오늘 일정 알려줘", input_source="voice")

        self.assertTrue(result.handled)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "calendar")
        self.assertIn("오늘 일정은 2건입니다", result.response)

    def test_default_registry_registers_calendar_ability(self):
        """Check Calendar is discoverable from the default ToolRegistry."""
        registry = create_default_tool_registry()

        self.assertTrue(registry.exists("calendar"))
        self.assertIn("calendar", registry.get("calendar").metadata.aliases)

    def test_weather_metadata_contains_required_manifest_fields(self):
        """Check Weather exposes the minimum Ability manifest."""
        metadata = WeatherAbility().metadata

        self.assertEqual(metadata.id, "weather")
        self.assertEqual(metadata.name, "Weather")
        self.assertEqual(metadata.type, AbilityType.NATIVE)
        self.assertEqual(metadata.permission, PermissionLevel.SAFE)
        self.assertEqual(metadata.description, "Current weather")
        self.assertEqual(metadata.author, "Jarvis")
        self.assertIn("type", metadata.input_schema)
        self.assertEqual(metadata.output_schema, "WeatherResult")
        self.assertIn("current_weather", metadata.capabilities)
        self.assertIn("forecast", metadata.capabilities)

    def test_ability_adapter_exposes_tool_metadata(self):
        """Check Ability metadata is translated for ToolRouter."""
        tool = AbilityToolAdapter(WeatherAbility())

        self.assertEqual(tool.metadata.name, "weather")
        self.assertEqual(tool.metadata.domain, "ability.native")
        self.assertEqual(tool.metadata.permission_level, PermissionLevel.SAFE)
        self.assertIn("weather", tool.metadata.input_prefixes)

    def test_weather_ability_runs_through_tool_dispatcher(self):
        """Check Weather can execute through the existing dispatcher path."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(WeatherAbility())
        ability_registry.register_tools(tool_registry)
        dispatcher = ToolDispatcher(registry=tool_registry)

        result = dispatcher.execute(
            ToolRequest(
                tool_name="weather",
                input_data={"text": "Seoul"},
            )
        )

        self.assertTrue(result.success)
        self.assertIsInstance(result.output, AbilityResult)
        self.assertEqual(result.output.data.location, "Seoul")
        self.assertEqual(result.output.data.provider, "mock")

    def test_weather_ability_routes_through_brain_tool_router(self):
        """Check ToolRouter can select Weather without Core-specific logic."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(WeatherAbility())
        ability_registry.register_tools(tool_registry)

        request = BrainToolRouter().plan("weather Seoul", registry=tool_registry)

        self.assertEqual(request.tool_name, "weather")
        self.assertEqual(request.input_data["text"], "Seoul")

    def test_weather_ability_routes_korean_weather_intent(self):
        """Check Korean weather requests route through ToolRouter."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(WeatherAbility())
        ability_registry.register_tools(tool_registry)

        request = BrainToolRouter().plan("오늘 날씨 알려줘", registry=tool_registry)

        self.assertEqual(request.tool_name, "weather")

    def test_ability_registry_rejects_duplicate_names(self):
        """Check ability names are unique."""
        registry = AbilityRegistry()
        registry.register(WeatherAbility())

        with self.assertRaises(ValueError):
            registry.register(WeatherAbility())

    def test_weather_ability_routes_location_before_korean_weather_keyword(self):
        """Check Korean location weather requests route through ToolRouter."""
        registry = create_mock_weather_tool_registry()

        request = BrainToolRouter().plan("\uc624\ub298 \uac15\ub989 \ub0a0\uc528 \uc54c\ub824\uc918", registry=registry)

        self.assertEqual(request.tool_name, "weather")
        self.assertEqual(request.input_data["text"], "\uc624\ub298 \uac15\ub989 \ub0a0\uc528 \uc54c\ub824\uc918")

    def test_weather_query_parses_today_location_current(self):
        """Check today weather request extracts location, date, and mode."""
        query = WeatherIntentParser().parse("\uc624\ub298 \uac15\ub989 \ub0a0\uc528 \uc54c\ub824\uc918")

        self.assertEqual(query.location, "\uac15\ub989")
        self.assertEqual(query.date, "today")
        self.assertEqual(query.mode, "current")
        self.assertEqual(query.capability, "current_weather")
        self.assertGreaterEqual(query.confidence, 0.95)

    def test_weather_location_resolver_maps_korean_locations_for_openweather(self):
        """Check Korean user locations resolve to OpenWeather city names."""
        resolver = WeatherLocationResolver()

        self.assertEqual(resolver.resolve("\uac15\ub989"), "Gangneung,KR")
        self.assertEqual(resolver.resolve("\uc7a0\uc2e4"), "Seoul,KR")
        self.assertEqual(resolver.resolve("\uc624\uc0ac\uce74"), "Osaka,JP")

    def test_openweather_provider_resolves_location_before_fetch(self):
        """Check OpenWeather receives resolved city names, not raw Korean text."""
        provider = CapturingOpenWeatherProvider(api_key="test-key")

        provider.get_weather(WeatherQuery(location="\uac15\ub989"))

        self.assertEqual(provider.seen_location, "Gangneung,KR")

    def test_openweather_provider_uses_configured_default_location(self):
        """Check missing weather locations use a real configured city for OpenWeather."""
        provider = CapturingOpenWeatherProvider(api_key="test-key", default_location="\uac15\ub989")

        result = provider.get_weather(WeatherQuery(location=None))

        self.assertEqual(provider.seen_location, "Gangneung,KR")
        self.assertEqual(result.location, "\uac15\ub989")
        self.assertEqual(result.provider, "openweather")

    def test_weather_query_parses_tomorrow_location_forecast(self):
        """Check tomorrow weather request becomes forecast mode."""
        query = WeatherIntentParser().parse("\ub0b4\uc77c \uc7a0\uc2e4 \ub0a0\uc528 \uc54c\ub824\uc918")

        self.assertEqual(query.location, "\uc7a0\uc2e4")
        self.assertEqual(query.date, "tomorrow")
        self.assertEqual(query.mode, "forecast")
        self.assertEqual(query.capability, "forecast")
        self.assertGreaterEqual(query.confidence, 0.95)

    def test_weather_query_parses_day_after_tomorrow_precipitation(self):
        """Check rain request extracts precipitation capability."""
        query = WeatherIntentParser().parse("\ubaa8\ub808 \uc11c\uc6b8 \ube44 \uc640?")

        self.assertEqual(query.location, "\uc11c\uc6b8")
        self.assertEqual(query.date, "day_after_tomorrow")
        self.assertEqual(query.mode, "forecast")
        self.assertEqual(query.capability, "precipitation")
        self.assertGreaterEqual(query.confidence, 0.95)

    def test_weather_router_matches_precipitation_question(self):
        """Check precipitation weather requests route without the weather word."""
        registry = create_mock_weather_tool_registry()

        request = BrainToolRouter().plan("\ubaa8\ub808 \uc11c\uc6b8 \ube44 \uc640?", registry=registry)

        self.assertEqual(request.tool_name, "weather")

    def test_weather_query_removes_current_time_word_from_location(self):
        """Check current-time words are not sent to providers as locations."""
        current_only = WeatherIntentParser().parse("\uc9c0\uae08 \ube44\uc640?")
        with_location = WeatherIntentParser().parse("\uac15\ub989 \uc9c0\uae08 \ube44\uc640?")
        outside = WeatherIntentParser().parse("\uc9c0\uae08 \ubc16\uc5d0 \ube44\uc640?")

        self.assertIsNone(current_only.location)
        self.assertIsNone(outside.location)
        self.assertEqual(current_only.capability, "precipitation")
        self.assertEqual(outside.capability, "precipitation")
        self.assertEqual(with_location.location, "\uac15\ub989")
        self.assertEqual(with_location.capability, "precipitation")

    def test_weather_query_parses_location_only_weather(self):
        """Check bare location weather request defaults to current today."""
        query = WeatherIntentParser().parse("\uac15\ub989 \ub0a0\uc528")

        self.assertEqual(query.location, "\uac15\ub989")
        self.assertEqual(query.date, "today")
        self.assertEqual(query.mode, "current")
        self.assertGreaterEqual(query.confidence, 0.95)

    def test_weather_query_uses_default_location_for_missing_location(self):
        """Check forecast request can use default location."""
        query = WeatherIntentParser().parse("\ub0b4\uc77c \ub0a0\uc528 \uc54c\ub824\uc918")

        self.assertIsNone(query.location)
        self.assertEqual(query.date, "tomorrow")
        self.assertEqual(query.mode, "forecast")
        self.assertLess(query.confidence, 0.8)

    def test_weather_query_missing_location_has_lower_confidence(self):
        """Check missing location leaves room for Memory Ability enrichment."""
        query = WeatherIntentParser().parse("\uc624\ub298 \ube44 \uc640?")

        self.assertIsNone(query.location)
        self.assertEqual(query.capability, "precipitation")
        self.assertLess(query.confidence, 0.8)

    def test_ability_registry_indexes_capabilities(self):
        """Check Registry can find abilities by declared capability."""
        registry = AbilityRegistry()
        registry.register(WeatherAbility())

        self.assertIn("current_weather", registry.list_capabilities("weather"))
        self.assertIn("forecast", registry.list_capabilities())
        self.assertEqual(registry.find_by_capability("humidity")[0].id, "weather")

    def test_mock_provider_returns_weather_result(self):
        """Check Mock Provider returns the shared WeatherResult object."""
        result = MockWeatherProvider().get_current_weather("강릉")

        self.assertIsInstance(result, WeatherResult)
        self.assertEqual(result.location, "강릉")
        self.assertEqual(result.precipitation_probability, 10)

    def test_weather_provider_can_be_replaced(self):
        """Check Weather Ability depends only on the provider interface."""
        ability = WeatherAbility(provider=StaticWeatherProvider())

        result = ability.execute({"location": "Busan"})

        self.assertIsInstance(result, AbilityResult)
        self.assertEqual(result.data.location, "Busan")
        self.assertEqual(result.data.provider, "static")
        self.assertEqual(result.data.temperature, 12.0)

    def test_weather_ability_executes_forecast_query(self):
        """Check Weather Ability preserves parsed forecast query fields."""
        ability = WeatherAbility(provider=MockWeatherProvider())

        result = ability.execute({"text": "\ub0b4\uc77c \uc7a0\uc2e4 \ub0a0\uc528 \uc54c\ub824\uc918"})

        self.assertTrue(result.success)
        self.assertEqual(result.data.location, "\uc7a0\uc2e4")
        self.assertEqual(result.data.date, "tomorrow")
        self.assertEqual(result.data.mode, "forecast")
        self.assertIn("\ub0b4\uc77c \uc7a0\uc2e4 \ub0a0\uc528\ub294", result.data.to_natural_language())

    def test_openweather_response_normalizes_to_weather_result(self):
        """Check OpenWeather JSON is normalized into WeatherResult."""
        result = normalize_openweather_response(
            {
                "name": "Gangneung",
                "dt": 1726660758,
                "weather": [{"description": "clear sky"}],
                "main": {
                    "temp": 27.5,
                    "feels_like": 28.0,
                    "humidity": 55,
                },
                "wind": {"speed": 3.2},
            }
        )

        self.assertEqual(result.location, "Gangneung")
        self.assertEqual(result.temperature, 27.5)
        self.assertEqual(result.provider, "openweather")
        self.assertEqual(result.precipitation_probability, 0)

    def test_config_creates_mock_weather_provider_by_default(self):
        """Check weather.provider defaults to mock."""
        provider = create_weather_provider(WeatherConfig())

        self.assertIsInstance(provider, MockWeatherProvider)

    def test_config_loader_reads_weather_provider_settings(self):
        """Check weather.provider config is loaded from config data."""
        config = create_config_from_dict(
            {
                "weather": {
                    "provider": "openweather",
                    "fallback_to_mock": False,
                    "openweather_lang": "kr",
                    "default_location": "\uc11c\uc6b8",
                }
            }
        )

        self.assertEqual(config.weather.provider, "openweather")
        self.assertFalse(config.weather.fallback_to_mock)
        self.assertEqual(config.weather.openweather_lang, "kr")
        self.assertEqual(config.weather.default_location, "\uc11c\uc6b8")

    def test_weather_default_location_env_override(self):
        """Check default weather location can be tuned without code edits."""
        previous = os.environ.get("JARVIS_WEATHER_DEFAULT_LOCATION")
        os.environ["JARVIS_WEATHER_DEFAULT_LOCATION"] = "\ubd80\uc0b0"

        try:
            config = create_config_from_dict({"weather": {"default_location": "\uc11c\uc6b8"}})
        finally:
            restore_env("JARVIS_WEATHER_DEFAULT_LOCATION", previous)

        self.assertEqual(config.weather.default_location, "\ubd80\uc0b0")

    def test_configured_weather_provider_passes_default_location(self):
        """Check provider factory carries default location into real providers."""
        config = WeatherConfig(provider="openweather", default_location="\uac15\ub989")

        provider = create_weather_provider(config)

        self.assertEqual(provider.default_location, "\uac15\ub989")

    def test_config_loader_reads_ai_intent_settings(self):
        """Check ai_intent config is loaded from config data."""
        config = create_config_from_dict(
            {
                "ai_intent": {
                    "enabled": True,
                    "provider": "openai",
                    "model": "gpt-intent-test",
                    "timeout": 6,
                    "min_confidence": 0.72,
                    "max_output_tokens": 240,
                    "reasoning_effort": "low",
                    "verbosity": "low",
                }
            }
        )

        self.assertTrue(config.ai_intent.enabled)
        self.assertEqual(config.ai_intent.provider, "openai")
        self.assertEqual(config.ai_intent.model, "gpt-intent-test")
        self.assertEqual(config.ai_intent.timeout, 6)
        self.assertEqual(config.ai_intent.min_confidence, 0.72)
        self.assertEqual(config.ai_intent.max_output_tokens, 240)
        self.assertEqual(config.ai_intent.reasoning_effort, "low")
        self.assertEqual(config.ai_intent.verbosity, "low")

    def test_openweather_provider_uses_mock_fallback_when_key_missing(self):
        """Check real provider failures can fall back to marked mock output."""
        provider = FallbackWeatherProvider(FailingWeatherProvider())

        result = provider.get_current_weather("Gangneung")

        self.assertEqual(result.provider, "mock_fallback")
        self.assertEqual(result.location, "Gangneung")

    def test_weather_health_reports_provider_status(self):
        """Check Weather health reports provider readiness."""
        health = WeatherAbility().health()

        self.assertIsInstance(health, AbilityHealth)
        self.assertTrue(health.ok)
        self.assertEqual(health.provider, "mock")

    @unittest.skipUnless(os.getenv("OPENWEATHER_API_KEY"), "OPENWEATHER_API_KEY is not set")
    def test_openweather_provider_integration_when_api_key_exists(self):
        """Check OpenWeather integration only when a real API key is present."""
        provider = OpenWeatherProvider()

        result = provider.get_current_weather("Gangneung,KR")

        self.assertIsInstance(result, WeatherResult)
        self.assertEqual(result.provider, "openweather")
        self.assertNotEqual(result.location, "")

    def test_weather_permission_is_safe(self):
        """Check Weather adapter remains eligible for safe routing."""
        tool = AbilityToolAdapter(WeatherAbility())

        self.assertEqual(tool.metadata.permission_level, PermissionLevel.SAFE)
        self.assertTrue(tool.metadata.safe)

    def test_default_registry_registers_weather_ability(self):
        """Check Weather is discoverable from the default ToolRegistry."""
        registry = create_default_tool_registry()

        self.assertTrue(registry.exists("weather"))

    def test_memory_metadata_contains_required_manifest_fields(self):
        """Check Memory exposes the persistent Ability manifest."""
        metadata = MemoryAbility(storage=InertMemoryStorage()).metadata

        self.assertEqual(metadata.id, "memory")
        self.assertEqual(metadata.name, "Memory")
        self.assertEqual(metadata.type, AbilityType.NATIVE)
        self.assertEqual(metadata.permission, PermissionLevel.SAFE)
        self.assertEqual(metadata.output_schema, "MemoryResult")
        self.assertIn("memory_remember", metadata.capabilities)
        self.assertIn("memory_recall", metadata.capabilities)

    def test_memory_parser_extracts_standard_user_name_key(self):
        """Check Korean remember text becomes a standard MemoryQuery."""
        query = MemoryIntentParser().parse("\ub0b4 \uc774\ub984\uc740 \ud06c\ub9ac\uc2a4\uc57c. \uc55e\uc73c\ub85c \uae30\uc5b5\ud574.")

        self.assertEqual(query.action, "remember")
        self.assertEqual(query.key, "user.name")
        self.assertEqual(query.value, "\ud06c\ub9ac\uc2a4")
        self.assertEqual(query.scope, "long_term")
        self.assertEqual(query.category, "profile")
        self.assertGreaterEqual(query.confidence, 0.95)

    def test_memory_parser_handles_long_remember_sentence(self):
        """Check long remember text keeps the full spoken value."""
        query = MemoryIntentParser().parse(
            "\uae30\uc5b5\ud574. \uc544\uc57c\ub791 \ucc98\uc74c \ub9cc\ub09c \ub0a0\uc740 2026\ub144 3\uc6d4 26\uc77c\uc774\uc57c."
        )

        self.assertEqual(query.action, "remember")
        self.assertEqual(query.key, "relationship.aya.first_meeting_date")
        self.assertEqual(query.value, "2026-03-26")
        self.assertEqual(query.scope, "long_term")

    def test_memory_parser_extracts_relationship_event_date(self):
        """Check relationship event memories preserve time metadata."""
        query = MemoryIntentParser().parse(
            "\uc544\uc57c\ub791 \ucc98\uc74c \ub9cc\ub09c \ub0a0\uc740 2026\ub144 3\uc6d4 26\uc77c\uc774\uc57c. \uae30\uc5b5\ud574."
        )

        self.assertEqual(query.action, "remember")
        self.assertEqual(query.key, "relationship.aya.first_meeting_date")
        self.assertEqual(query.value, "2026-03-26")
        self.assertEqual(query.category, "relationship")
        self.assertEqual(query.event["type"], "event")
        self.assertEqual(query.event["title"], "\uc544\uc57c\uc640 \ucc98\uc74c \ub9cc\ub09c \ub0a0")
        self.assertEqual(query.event["people"], ["\uc544\uc57c"])
        self.assertEqual(query.event["date"], "2026-03-26")

    def test_memory_parser_recalls_relationship_event_key(self):
        """Check natural recall text maps to the same relationship event key."""
        query = MemoryIntentParser().parse("\uc544\uc57c\ub791 \ucc98\uc74c \ub9cc\ub09c \uac8c \uc5b8\uc81c\uc600\uc9c0?")

        self.assertEqual(query.action, "recall")
        self.assertEqual(query.key, "relationship.aya.first_meeting_date")

    def test_memory_parser_canonicalizes_aya_birthday_key(self):
        """Check Aya birthday remember/recall use one canonical relationship key."""
        parser = MemoryIntentParser()
        remember_query = parser.parse("기억해 아야 생일은 1991년 2월 28일이야")
        recall_cases = [
            "아야 생일 언제야",
            "아야 생일이 언제였지",
            "아야 생일 알려줘",
        ]

        self.assertEqual(remember_query.action, "remember")
        self.assertEqual(remember_query.key, "relationship.aya.birthday")
        self.assertEqual(remember_query.value, "1991-02-28")
        self.assertEqual(remember_query.category, "relationship")
        self.assertEqual(remember_query.event["title"], "아야 생일")
        self.assertEqual(remember_query.event["date"], "1991-02-28")

        for text in recall_cases:
            with self.subTest(text=text):
                recall_query = parser.parse(text)
                self.assertEqual(recall_query.action, "recall")
                self.assertEqual(recall_query.key, "relationship.aya.birthday")

    def test_memory_parser_traces_canonical_key(self):
        """Check debug trace exposes source text and canonical memory key."""
        output = io.StringIO()

        with patch.dict(
            os.environ,
            {"JARVIS_DEBUG_TRACE": "true", "JARVIS_TRACE_RAW": "", "JARVIS_MEMORY_TRACE_VERBOSE": "true"},
            clear=False,
        ):
            with redirect_stdout(output):
                MemoryIntentParser().parse("아야 생일 언제야")

        self.assertIn('[Memory] canonical_key source_text="아야 생일 언제야"', output.getvalue())
        self.assertIn("canonical_key=relationship.aya.birthday", output.getvalue())

    def test_memory_parser_uses_canonical_relationship_name_after_stt_correction(self):
        """Check corrected STT proper names generate the canonical memory key."""
        from jarvis.voice.user_vocabulary import normalize_stt_text

        remember_text = normalize_stt_text(
            "\uc544\uc774\uc640 \ucc98\uc74c \ub9cc\ub09c \ub0a0\uc740 2026\ub144 3\uc6d4 26\uc77c\uc774\uc57c. \uae30\uc5b5\ud574."
        ).normalized_text
        recall_text = normalize_stt_text(
            "\uc544\uc774\uc544 \ucc98\uc74c \ub9cc\ub09c \uac8c \uc5b8\uc81c\uc600\uc9c0?"
        ).normalized_text

        remember_query = MemoryIntentParser().parse(remember_text)
        recall_query = MemoryIntentParser().parse(recall_text)

        self.assertEqual(remember_query.key, "relationship.aya.first_meeting_date")
        self.assertEqual(recall_query.key, "relationship.aya.first_meeting_date")

    def test_memory_ability_remember_recall_update_forget(self):
        """Check Memory can remember, recall, update, and forget entries."""
        ability = MemoryAbility(storage=InertMemoryStorage())

        remembered = ability.execute(
            {
                "action": "remember",
                "key": "user.name",
                "value": "\ud06c\ub9ac\uc2a4",
                "category": "profile",
                "scope": "long_term",
                "confidence": 0.97,
            }
        )
        recalled = ability.execute({"action": "recall", "key": "user.name", "scope": "long_term"})
        updated = ability.execute(
            {
                "action": "remember",
                "key": "user.name",
                "value": "Chris",
                "category": "profile",
                "scope": "long_term",
            }
        )
        recalled_after_update = ability.execute({"action": "recall", "key": "user.name", "scope": "long_term"})
        forgotten = ability.execute({"action": "forget", "key": "user.name", "scope": "long_term", "_confirmed": True})
        recalled_after_forget = ability.execute({"action": "recall", "key": "user.name", "scope": "long_term"})

        self.assertTrue(remembered.success)
        self.assertIsInstance(remembered.data, MemoryResult)
        self.assertEqual(recalled.data.entry.value, "\ud06c\ub9ac\uc2a4")
        self.assertEqual(updated.data.entry.id, remembered.data.entry.id)
        self.assertEqual(recalled_after_update.data.entry.value, "Chris")
        self.assertTrue(forgotten.data.found)
        self.assertFalse(recalled_after_forget.data.found)

    def test_memory_json_storage_persists_across_restart(self):
        """Check Memory survives storage/provider recreation."""
        path = os.path.join("output", "test_memory_persistence.json")
        remove_test_file(path)

        try:
            ability = MemoryAbility(storage=JsonMemoryStorage(path=path))
            remembered = ability.execute(
                {
                    "action": "remember",
                    "key": "user.name",
                    "value": "\ud06c\ub9ac\uc2a4",
                    "category": "profile",
                    "scope": "long_term",
                }
            )
            self.assertTrue(remembered.success)

            restarted = MemoryAbility(storage=JsonMemoryStorage(path=path))
            result = restarted.execute({"action": "recall", "key": "user.name", "scope": "long_term"})
        finally:
            remove_test_file(path)

        self.assertTrue(result.success)
        self.assertEqual(result.data.entry.value, "\ud06c\ub9ac\uc2a4")
        self.assertEqual(result.data.to_natural_language(), "\ud06c\ub9ac\uc2a4\uc785\ub2c8\ub2e4.")

    def test_memory_event_metadata_persists_across_restart(self):
        """Check event metadata survives JSON storage recreation."""
        path = os.path.join("output", "test_memory_event_persistence.json")
        remove_test_file(path)

        try:
            ability = MemoryAbility(storage=JsonMemoryStorage(path=path))
            remembered = ability.execute(
                {
                    "text": "\uc544\uc57c\ub791 \ucc98\uc74c \ub9cc\ub09c \ub0a0\uc740 2026\ub144 3\uc6d4 26\uc77c\uc774\uc57c. \uae30\uc5b5\ud574."
                }
            )
            restarted = MemoryAbility(storage=JsonMemoryStorage(path=path))
            result = restarted.execute(
                {"text": "\uc544\uc57c\ub791 \ucc98\uc74c \ub9cc\ub09c \uac8c \uc5b8\uc81c\uc600\uc9c0?"}
            )
        finally:
            remove_test_file(path)

        self.assertTrue(remembered.success)
        self.assertTrue(result.success)
        self.assertEqual(result.data.entry.key, "relationship.aya.first_meeting_date")
        self.assertEqual(result.data.entry.value, "2026-03-26")
        self.assertEqual(result.data.entry.event["date"], "2026-03-26")
        self.assertEqual(result.data.to_natural_language(), "2026\ub144 3\uc6d4 26\uc77c\uc5d0 \ucc98\uc74c \ub9cc\ub098\uc168\uc2b5\ub2c8\ub2e4.")

    def test_memory_remember_is_safe_but_forget_requires_confirmation(self):
        """Check remember can run immediately while forget requires confirmation."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(MemoryAbility(storage=InertMemoryStorage()))
        ability_registry.register_tools(tool_registry)
        dispatcher = ToolDispatcher(tool_registry)

        remembered = dispatcher.execute(
            ToolRequest(
                tool_name="memory",
                input_data={"action": "remember", "key": "user.name", "value": "\ud06c\ub9ac\uc2a4"},
            )
        )
        forget_without_confirm = dispatcher.execute(
            ToolRequest(
                tool_name="memory",
                input_data={"action": "forget", "key": "user.name"},
            )
        )
        forget_confirmed = dispatcher.execute(
            ToolRequest(
                tool_name="memory",
                input_data={
                    "action": "forget",
                    "key": "user.name",
                    "_confirmed": True,
                },
            )
        )

        self.assertTrue(remembered.success)
        self.assertTrue(forget_without_confirm.success)
        self.assertIn("\ud655\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4", forget_without_confirm.output.to_natural_language())
        self.assertTrue(forget_confirmed.success)
        self.assertTrue(forget_confirmed.output.data.found)

    def test_memory_remember_routes_through_intent_runtime_without_confirmation(self):
        """Check Memory remember executes through IntentRuntime."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(MemoryAbility(storage=InertMemoryStorage()))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))

        result = runtime.run("\ub0b4 \uc774\ub984\uc740 \ud06c\ub9ac\uc2a4\uc57c. \uc55e\uc73c\ub85c \uae30\uc5b5\ud574.", input_source="voice")

        self.assertTrue(result.handled)
        self.assertTrue(result.success)
        self.assertEqual(result.intent.tool_name, "memory")
        self.assertEqual(result.permission_status, "allowed")
        self.assertIn("\uc7a5\uae30 \uae30\uc5b5\uc5d0 \uc800\uc7a5\ud588\uc2b5\ub2c8\ub2e4", result.response)

    def test_memory_long_sentence_routes_through_intent_runtime(self):
        """Check the voice test remember sentence routes and stores."""
        storage = InertMemoryStorage()
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(MemoryAbility(storage=storage))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))

        result = runtime.run(
            "\uae30\uc5b5\ud574. \uc544\uc57c\ub791 \ucc98\uc74c \ub9cc\ub09c \ub0a0\uc740 2026\ub144 3\uc6d4 26\uc77c\uc774\uc57c.",
            input_source="voice",
        )

        self.assertTrue(result.success)
        self.assertEqual(storage.get("relationship.aya.first_meeting_date").value, "2026-03-26")

    def test_memory_relationship_recall_routes_through_intent_runtime(self):
        """Check natural relationship recall routes to Memory instead of LLM."""
        storage = InertMemoryStorage()
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability = MemoryAbility(storage=storage)
        ability.execute(
            {
                "text": "\uc544\uc57c\ub791 \ucc98\uc74c \ub9cc\ub09c \ub0a0\uc740 2026\ub144 3\uc6d4 26\uc77c\uc774\uc57c. \uae30\uc5b5\ud574."
            }
        )
        ability_registry.register(ability)
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))

        result = runtime.run("\uc544\uc57c \ucc98\uc74c \ub9cc\ub09c \ub0a0\uc774 \uc5b8\uc81c\uc57c", input_source="voice")

        self.assertTrue(result.handled)
        self.assertTrue(result.success)
        self.assertEqual(result.intent.tool_name, "memory")
        self.assertEqual(result.tool_name, "memory")
        self.assertIn("2026\ub144 3\uc6d4 26\uc77c", result.response)

    def test_memory_birthday_recall_uses_same_canonical_key_as_remember(self):
        """Check stored Aya birthday is recalled through the same canonical key."""
        storage = InertMemoryStorage()
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability = MemoryAbility(storage=storage)
        remember_result = ability.execute({"text": "기억해 아야 생일은 1991년 2월 28일이야"})
        ability_registry.register(ability)
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))

        result = runtime.run("아야 생일 언제야", input_source="voice")

        self.assertTrue(remember_result.success)
        self.assertEqual(remember_result.data.entry.key, "relationship.aya.birthday")
        self.assertTrue(result.handled)
        self.assertTrue(result.success)
        self.assertEqual(result.intent.tool_name, "memory")
        self.assertEqual(result.tool_name, "memory")
        self.assertIn("1991년 2월 28일", result.response)

    def test_memory_birthday_recall_migrates_legacy_general_key(self):
        """Check old general Aya birthday key still resolves to canonical recall."""
        storage = InertMemoryStorage()
        storage.upsert(
            MemoryEntry(
                id="legacy-birthday",
                key="general.아야_생일",
                value="1991년 2월 28일",
                category="relationship",
                scope="long_term",
                confidence=0.96,
            )
        )
        ability = MemoryAbility(storage=storage)

        result = ability.execute({"text": "아야 생일 언제야"})

        self.assertTrue(result.success)
        self.assertTrue(result.data.found)
        self.assertEqual(result.data.entry.key, "relationship.aya.birthday")
        self.assertEqual(result.data.entry.value, "1991-02-28")
        self.assertIn("1991년 2월 28일", result.data.to_natural_language())
        self.assertIsNotNone(storage.get("relationship.aya.birthday"))

    def test_memory_summary_trace_compacts_recall_debug_info(self):
        """Check Memory emits one compact summary trace for recall debugging."""
        storage = InertMemoryStorage()
        storage.upsert(
            MemoryEntry(
                id="legacy-birthday",
                key="general.아야_생일",
                value="1991년 2월 28일",
                category="relationship",
                scope="long_term",
                confidence=0.96,
            )
        )
        ability = MemoryAbility(storage=storage)
        output = io.StringIO()

        with patch.dict(
            os.environ,
            {"JARVIS_DEBUG_TRACE": "true", "JARVIS_TRACE_RAW": "", "JARVIS_MEMORY_TRACE_VERBOSE": "false"},
            clear=False,
        ):
            with redirect_stdout(output):
                ability.execute({"text": "아야 생일 언제야"})

        trace_output = output.getvalue()

        self.assertIn("[Memory] intent=recall", trace_output)
        self.assertNotIn("[Memory] canonical_key", trace_output)
        self.assertNotIn("[Memory] query", trace_output)
        self.assertNotIn("[Memory] result", trace_output)
        self.assertIn("entity=aya", trace_output)
        self.assertIn("attribute=birthday", trace_output)
        self.assertIn("canonical_key=relationship.aya.birthday", trace_output)
        self.assertIn("source=legacy", trace_output)
        self.assertIn("found=YES", trace_output)
        self.assertIn("value=1991-02-28", trace_output)
        self.assertRegex(trace_output, r"duration=\d+ms")

    def test_default_registry_registers_memory_ability(self):
        """Check Memory is discoverable from the default ToolRegistry."""
        registry = create_default_tool_registry()

        self.assertTrue(registry.exists("memory"))
        self.assertEqual(registry.get("memory").metadata.permission_level, PermissionLevel.SAFE)
        self.assertTrue(registry.get("memory").metadata.safe)

    def test_weather_intent_runtime_formats_ability_result_for_tts(self):
        """Check Voice IntentRuntime returns spoken Weather text without LLM fallback."""
        from jarvis.brain import IntentRuntime

        dispatcher = ToolDispatcher(create_mock_weather_tool_registry())
        runtime = IntentRuntime(tool_dispatcher=dispatcher)

        result = runtime.run("\uc624\ub298 \uac15\ub989 \ub0a0\uc528 \uc54c\ub824\uc918", input_source="voice")

        self.assertTrue(result.handled)
        self.assertTrue(result.success)
        self.assertEqual(result.tool, "weather")
        self.assertIn("\ud604\uc7ac \uac15\ub989\uc740", result.response)

    def test_weather_response_formats_for_tts(self):
        """Check WeatherResult becomes natural language for voice output."""
        registry = create_mock_weather_tool_registry()
        context = ChatCommandContext(
            chat_service=CapturingChatService(),
            tool_dispatcher=ToolDispatcher(registry),
            command_text="weather 강릉",
        )

        output = ChatCommand().execute(context)

        self.assertIn("현재 강릉은 27도이며 맑음입니다", output)
        self.assertIn("강수확률은 10%입니다", output)
        self.assertEqual(context.chat_service.messages, [])

    def test_weather_response_does_not_speak_provider_debug(self):
        """Check provider debug stays in trace logs, not spoken weather text."""
        previous_debug = os.environ.get("JARVIS_DEBUG_TRACE")
        os.environ["JARVIS_DEBUG_TRACE"] = "true"

        try:
            result = WeatherResult(
                location="강릉",
                temperature=27,
                feels_like=28,
                condition="맑음",
                humidity=45,
                wind_speed=2.0,
                precipitation_probability=10,
                provider="openweather",
                timestamp="2026-07-13T14:31:00",
            )

            spoken = result.to_natural_language()

            self.assertNotIn("provider=", spoken)
            self.assertNotIn("openweather", spoken)
        finally:
            if previous_debug is None:
                os.environ.pop("JARVIS_DEBUG_TRACE", None)
            else:
                os.environ["JARVIS_DEBUG_TRACE"] = previous_debug


class StaticWeatherProvider:
    """Weather provider stub used to verify replacement."""

    provider_name = "static"

    def get_weather(self, query):
        """Return static weather data for a parsed query."""
        return self.get_current_weather(query.location)

    def get_current_weather(self, location):
        """Return static weather data for tests."""
        return WeatherResult(
            location=location,
            temperature=12.0,
            feels_like=11.0,
            condition="흐림",
            humidity=70,
            wind_speed=4.0,
            precipitation_probability=30,
            provider=self.provider_name,
            timestamp="2026-07-09T00:00:00",
        )


class FailingWeatherProvider:
    """Provider stub that always fails to verify fallback behavior."""

    provider_name = "failing"

    def get_current_weather(self, location):
        """Raise a deterministic provider failure."""
        raise RuntimeError("provider failed")


class CapturingOpenWeatherProvider(OpenWeatherProvider):
    """OpenWeather provider test double that captures the fetch location."""

    def __init__(self, api_key="test-key", default_location=None):
        """Create a capturing provider."""
        super().__init__(api_key=api_key, default_location=default_location)
        self.seen_location = None

    def fetch_current_weather(self, location):
        """Capture resolved location and return fake API data."""
        self.seen_location = location
        return {
            "name": "Gangneung",
            "dt": 1726660758,
            "weather": [{"description": "clear sky"}],
            "main": {
                "temp": 20.0,
                "feels_like": 21.0,
                "humidity": 50,
            },
            "wind": {"speed": 2.0},
        }


def restore_env(key, previous):
    """Restore one environment variable after a test override."""
    if previous is None:
        os.environ.pop(key, None)
        return

    os.environ[key] = previous


class CapturingChatService:
    """Chat service test double that records fallback calls."""

    def __init__(self):
        """Create an empty capture."""
        self.messages = []

    def generate_reply(self, message):
        """Record fallback chat messages."""
        self.messages.append(message)
        return "chat reply"


class InertMemoryStorage:
    """Memory storage test double."""

    provider_name = "inert"

    def __init__(self):
        """Create an empty storage."""
        self.entries = []

    def upsert(self, entry):
        """Create or update one entry."""
        self.entries = [
            existing
            for existing in self.entries
            if not (existing.key == entry.key and existing.scope == entry.scope)
        ]
        self.entries.append(entry)
        return entry

    def get(self, key, scope=None):
        """Return one matching entry."""
        candidates = [
            entry
            for entry in self.entries
            if entry.key == key and (scope is None or entry.scope == scope)
        ]
        return candidates[-1] if candidates else None

    def delete(self, key, scope=None):
        """Delete matching entries."""
        deleted = [
            entry
            for entry in self.entries
            if entry.key == key and (scope is None or entry.scope == scope)
        ]
        self.entries = [
            entry
            for entry in self.entries
            if not (entry.key == key and (scope is None or entry.scope == scope))
        ]
        return deleted

    def list(self, scope=None, category=None):
        """List entries."""
        entries = list(self.entries)

        if scope is not None:
            entries = [entry for entry in entries if entry.scope == scope]

        if category is not None:
            entries = [entry for entry in entries if entry.category == category]

        return entries


class NullEventBus:
    """Event bus used by chat command tests."""

    def publish_state(self, event_type, state):
        """Ignore published command state."""
        return None


class ChatCommandContext:
    """Minimal context for ChatCommand tests."""

    def __init__(self, chat_service, tool_dispatcher, command_text):
        """Create a chat command context."""
        self.chat_service = chat_service
        self.tool_dispatcher = tool_dispatcher
        self.command_text = command_text
        self.event_bus = NullEventBus()


def create_mock_weather_tool_registry():
    """Create a default tool registry pinned to mock weather."""
    config = create_config_from_dict(
        {
            "weather": {
                "provider": "mock",
            }
        }
    )
    return create_default_tool_registry(config=config)


def remove_test_file(path):
    """Remove a test file when present."""
    try:
        os.remove(path)
    except OSError:
        return


if __name__ == "__main__":
    unittest.main()
