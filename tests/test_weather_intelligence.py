import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from jarvis.abilities.native.weather import WeatherResult
from jarvis.abilities.native.weather import WeatherIntentParser
from jarvis.abilities.native.weather.provider import (
    WeatherForecastUnavailableError,
    validate_forecast_horizon,
)
from jarvis.abilities.native.weather.resolver import (
    ResolvedWeatherLocation,
    WeatherLocationCache,
)
from jarvis.runtime.date_resolver import DateResolver
from jarvis.runtime.context_merge import ContextValueSource, merge_context_value
from jarvis.runtime.language import LanguageContext
from jarvis.voice.pipeline import VoicePipeline


def weather_result(location="Osaka", mode="current", date_value="today"):
    return WeatherResult(
        location=location,
        temperature=27,
        feels_like=28,
        condition="\ub9d1\uc74c",
        humidity=60,
        wind_speed=2,
        precipitation_probability=10,
        provider="openweather",
        timestamp="2026-07-28T12:00:00+09:00",
        mode=mode,
        date=date_value,
        date_label="\ub0b4\uc77c" if date_value == "tomorrow" else "\uc624\ub298",
        temperature_min=24 if mode == "forecast" else None,
        temperature_max=31 if mode == "forecast" else None,
    )


class TestWeatherIntelligence(unittest.TestCase):
    def test_context_merge_precedence_is_explicit_then_context_then_default(self):
        explicit = merge_context_value(
            explicit="\ubd80\uc0b0",
            conversation="\uc11c\uc6b8",
            user_preference="\uac15\ub989",
            config_default="\uc81c\uc8fc",
        )
        conversation = merge_context_value(
            conversation="\uc11c\uc6b8",
            user_preference="\uac15\ub989",
            config_default="\uc81c\uc8fc",
        )

        self.assertEqual((explicit.value, explicit.source), ("\ubd80\uc0b0", ContextValueSource.EXPLICIT))
        self.assertEqual(
            (conversation.value, conversation.source),
            ("\uc11c\uc6b8", ContextValueSource.CONVERSATION),
        )

    def test_geocoding_cache_expires_by_ttl(self):
        now = [1000.0]
        cache_path = Path("output/cache/test_weather_intelligence.json")
        try:
            cache = WeatherLocationCache(
                cache_path,
                ttl_seconds=60,
                clock=lambda: now[0],
            )
            location = ResolvedWeatherLocation(
                original="\u672d\u5e4c",
                normalized="\u672d\u5e4c",
                canonical_name="Sapporo",
                country_code="JP",
                provider_query="Sapporo,JP",
                latitude=43.0618,
                longitude=141.3545,
                resolution_source="geocoding",
            )
            cache.put("\u672d\u5e4c", location)
            self.assertEqual(cache.get("\u672d\u5e4c").canonical_name, "Sapporo")
            now[0] += 61
            self.assertIsNone(cache.get("\u672d\u5e4c"))
        finally:
            cache_path.unlink(missing_ok=True)

    def test_weather_follow_up_reuses_last_location(self):
        pipeline = VoicePipeline(None, None, None, None)
        pipeline.weather_conversation_context = {"location": "Osaka"}

        self.assertEqual(
            pipeline.enrich_weather_follow_up("\ub0b4\uc77c\uc740?"),
            "Osaka \ub0b4\uc77c\uc740? \ub0a0\uc528",
        )
        self.assertEqual(
            pipeline.enrich_weather_follow_up("\ubaa8\ub808 \ube44 \uc640?"),
            "Osaka \ubaa8\ub808 \ube44 \uc640?",
        )

    def test_explicit_follow_up_location_overrides_conversation_location(self):
        pipeline = VoicePipeline(None, None, None, None)
        pipeline.weather_conversation_context = {"location": "\uc11c\uc6b8"}

        self.assertEqual(
            pipeline.enrich_weather_follow_up("\ub0b4\uc77c \ubd80\uc0b0\uc740?"),
            "\ub0b4\uc77c \ubd80\uc0b0\uc740? \ub0a0\uc528",
        )
        parsed = WeatherIntentParser().parse(
            pipeline.enrich_weather_follow_up("\ub0b4\uc77c \ubd80\uc0b0\uc740?")
        )
        self.assertEqual(parsed.location, "\ubd80\uc0b0")
        self.assertEqual(parsed.date, "tomorrow")

    def test_english_discourse_follow_up_reuses_conversation_location(self):
        pipeline = VoicePipeline(None, None, None, None)
        pipeline.weather_conversation_context = {"location": "Osaka"}

        enriched = pipeline.enrich_weather_follow_up("How about tomorrow?")
        parsed = WeatherIntentParser().parse(enriched)

        self.assertEqual(enriched, "Osaka How about tomorrow? \ub0a0\uc528")
        self.assertEqual(parsed.location, "Osaka")
        self.assertEqual(parsed.date, "tomorrow")
        self.assertTrue(pipeline.last_weather_intent.follow_up)
        self.assertEqual(pipeline.last_weather_intent.location, "Osaka")
        self.assertEqual(
            pipeline.last_weather_intent.location_source,
            "conversation_context",
        )
        self.assertEqual(pipeline.last_weather_intent.date_source, "explicit")
        self.assertEqual(
            pipeline.last_weather_intent.utterance,
            "How about tomorrow?",
        )

    def test_non_weather_follow_up_does_not_create_weather_intent(self):
        pipeline = VoicePipeline(None, None, None, None)
        pipeline.weather_conversation_context = {"location": "Osaka"}

        text = pipeline.enrich_weather_follow_up(
            "\uc774\uc81c \uc77c\ubc18 \ubaa8\ub4dc\ub85c \ub3cc\uc544\uc640."
        )

        self.assertEqual(
            text,
            "\uc774\uc81c \uc77c\ubc18 \ubaa8\ub4dc\ub85c \ub3cc\uc544\uc640.",
        )
        self.assertIsNone(pipeline.last_weather_intent)

    def test_english_discourse_follow_up_keeps_explicit_location(self):
        parser = WeatherIntentParser()

        query = parser.parse("How about Busan tomorrow?")

        self.assertEqual(query.location, "Busan")
        self.assertEqual(query.date, "tomorrow")

    def test_english_discourse_only_phrases_are_not_locations(self):
        parser = WeatherIntentParser()

        self.assertIsNone(parser.parse("What about today?").location)
        self.assertIsNone(parser.parse("And tomorrow?").location)
        self.assertIsNone(parser.parse("Then tomorrow?").location)

    def test_mock_weather_result_does_not_poison_conversation_context(self):
        pipeline = VoicePipeline(None, None, None, None)
        pipeline.weather_conversation_context = {"location": "\uc11c\uc6b8"}
        result = SimpleNamespace(
            tool="weather",
            tool_name="weather",
            success=True,
            tool_output=SimpleNamespace(
                data=WeatherResult(
                    **{
                        **weather_result("\uc11c\uc6b8 \ubd80\uc0b0").__dict__,
                        "provider": "mock_fallback",
                    }
                )
            ),
        )

        pipeline.remember_weather_context(result)

        self.assertEqual(pipeline.weather_conversation_context["location"], "\uc11c\uc6b8")

    def test_weather_context_corrects_narrow_morae_stt_variants(self):
        pipeline = VoicePipeline(None, None, None, None)
        pipeline.weather_conversation_context = {"location": "\uc624\uc0ac\uce74"}

        self.assertEqual(
            pipeline.normalize_weather_follow_up_stt("\ubaa8\ub798\uc640?"),
            "\ubaa8\ub808\ub294?",
        )
        self.assertEqual(
            pipeline.normalize_weather_follow_up_stt("\ubaa8\ub798\ube44\uc640"),
            "\ubaa8\ub808 \ube44 \uc640?",
        )

    def test_weather_stt_correction_does_not_run_without_weather_context(self):
        pipeline = VoicePipeline(None, None, None, None)

        self.assertEqual(
            pipeline.normalize_weather_follow_up_stt("\ubaa8\ub798\uc640?"),
            "\ubaa8\ub798\uc640?",
        )

    def test_successful_weather_result_updates_context(self):
        pipeline = VoicePipeline(None, None, None, None)
        result = SimpleNamespace(
            tool="weather",
            tool_name="weather",
            success=True,
            tool_output=SimpleNamespace(data=weather_result("Osaka")),
        )

        pipeline.remember_weather_context(result)

        self.assertEqual(pipeline.weather_conversation_context["location"], "Osaka")
        self.assertEqual(pipeline.weather_conversation_context["provider"], "openweather")

    def test_weather_formatter_uses_response_language_without_llm(self):
        pipeline = VoicePipeline(None, None, None, None)
        pipeline.language_context = LanguageContext(
            detected_language="ko",
            response_language="ja",
        )
        result = SimpleNamespace(
            tool="weather",
            tool_name="weather",
            tool_output=SimpleNamespace(
                data=weather_result("Osaka", mode="forecast", date_value="tomorrow")
            ),
        )

        response = pipeline.structured_ability_response(result, "fallback")

        self.assertIn("Osaka\u306e\u660e\u65e5\u306e\u5929\u6c17", response)
        self.assertIn("\u6674\u308c", response)

    def test_weather_formatter_translates_korean_heavy_rain_to_japanese(self):
        base = weather_result("Osaka")
        result = WeatherResult(
            **{
                **base.__dict__,
                "condition": "\uac15\ud55c \ube44",
            }
        )

        response = result.to_natural_language("ja")

        self.assertIn("\u5927\u96e8", response)
        self.assertNotIn("\uac15\ud55c \ube44", response)

    def test_weather_formatter_uses_language_specific_resolved_location(self):
        base = weather_result("\uc624\uc0ac\uce74", mode="forecast", date_value="tomorrow")
        result = WeatherResult(
            **{
                **base.__dict__,
                "location_names": {
                    "ko": "\uc624\uc0ac\uce74",
                    "ja": "\u5927\u962a",
                    "en": "Osaka",
                },
            }
        )

        self.assertIn("Tomorrow in Osaka", result.to_natural_language("en"))
        self.assertNotIn("\uc624\uc0ac\uce74", result.to_natural_language("en"))
        self.assertIn("\u5927\u962a\u306e\u660e\u65e5\u306e\u5929\u6c17", result.to_natural_language("ja"))
        self.assertIn("\ub0b4\uc77c \uc624\uc0ac\uce74", result.to_natural_language("ko"))

    def test_date_resolver_handles_ranges_weekday_and_explicit_date(self):
        resolver = DateResolver(today_provider=lambda: date(2026, 7, 28))

        self.assertEqual(resolver.resolve("\ub0b4\uc77c").start_date, "2026-07-29")
        self.assertEqual(
            resolver.resolve("\ub2e4\uc74c\uc8fc \ud654\uc694\uc77c").start_date,
            "2026-08-04",
        )
        weekend = resolver.resolve("\uc774\ubc88 \uc8fc\ub9d0")
        self.assertEqual((weekend.start_date, weekend.end_date), ("2026-08-01", "2026-08-02"))
        self.assertEqual(resolver.resolve("8\uc6d4 15\uc77c").start_date, "2026-08-15")

    def test_weather_parser_separates_explicit_date_from_location(self):
        parser = WeatherIntentParser(
            date_resolver=DateResolver(today_provider=lambda: date(2026, 7, 28))
        )

        query = parser.parse("8\uc6d4 14\uc77c \ubd80\uc0b0 \ub0a0\uc528 \uc54c\ub824\uc918")

        self.assertEqual(query.location, "\ubd80\uc0b0")
        self.assertEqual(query.date, "2026-08-14")
        self.assertEqual(query.mode, "forecast")
        self.assertEqual(query.date_label, "8\uc6d4 14\uc77c")

    def test_weather_explicit_date_outside_provider_horizon_is_not_mocked(self):
        parser = WeatherIntentParser(
            date_resolver=DateResolver(today_provider=lambda: date(2026, 7, 28))
        )
        query = parser.parse("8\uc6d4 14\uc77c \ubd80\uc0b0 \ub0a0\uc528")

        with self.assertRaisesRegex(
            WeatherForecastUnavailableError,
            "\uc624\ub298\ubd80\ud130 5\uc77c \uc774\ub0b4",
        ):
            validate_forecast_horizon(
                query,
                today_value=date(2026, 7, 28),
                horizon_days=5,
            )

    def test_weather_result_declares_weather_report_semantic_type(self):
        self.assertEqual(weather_result().semantic_type, "WeatherReport")


if __name__ == "__main__":
    unittest.main()
