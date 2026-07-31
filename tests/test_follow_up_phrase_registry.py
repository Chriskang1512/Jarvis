import unittest
from datetime import date

from jarvis.abilities.native.weather.parser import WeatherIntentParser
from jarvis.runtime import DateResolver, FollowUpPhraseRegistry
from jarvis.goals.parser import build_semantic_context
from jarvis.runtime.intent import IntentContext
from jarvis.voice.pipeline import VoicePipeline


class TestFollowUpPhraseRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = FollowUpPhraseRegistry()

    def test_english_follow_up_variants(self):
        for phrase in (
            "How about tomorrow?",
            "What about next week?",
            "And tomorrow?",
            "Then?",
            "How's Friday?",
            "Friday?",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(self.registry.match(phrase).is_follow_up)

    def test_japanese_follow_up_variants(self):
        for phrase in (
            "じゃあ明日は？",
            "では明後日は？",
            "あした？",
            "金曜日？",
        ):
            with self.subTest(phrase=phrase):
                match = self.registry.match(phrase)
                self.assertTrue(match.is_follow_up)
                self.assertEqual("ja", match.language)

    def test_korean_follow_up_variants(self):
        for phrase in (
            "그럼 내일은?",
            "그러면 모레는?",
            "내일은?",
            "금요일은?",
        ):
            with self.subTest(phrase=phrase):
                match = self.registry.match(phrase)
                self.assertTrue(match.is_follow_up)
                self.assertEqual("ko", match.language)

    def test_and_in_normal_sentence_is_not_follow_up_without_context_marker_shape(self):
        self.assertFalse(
            self.registry.match(
                "I need calendar and email updates tomorrow afternoon"
            ).is_follow_up
        )

    def test_weather_uses_registry_for_friday_follow_up(self):
        pipeline = VoicePipeline(None, None, None, None)
        pipeline.weather_conversation_context = {"location": "Osaka"}

        enriched = pipeline.enrich_weather_follow_up("How's Friday?")
        parsed = WeatherIntentParser().parse(enriched)

        self.assertEqual("Osaka How's Friday? 날씨", enriched)
        self.assertEqual("Osaka", parsed.location)
        self.assertRegex(parsed.date, r"\d{4}-\d{2}-\d{2}")
        self.assertTrue(pipeline.last_weather_intent.follow_up)

    def test_weather_reuses_location_for_japanese_and_korean_phrases(self):
        pipeline = VoicePipeline(None, None, None, None)
        pipeline.weather_conversation_context = {"location": "Osaka"}

        self.assertEqual(
            "Osaka じゃあ明日は？ 날씨",
            pipeline.enrich_weather_follow_up("じゃあ明日は？"),
        )
        self.assertEqual(
            "Osaka 그럼 내일은? 날씨",
            pipeline.enrich_weather_follow_up("그럼 내일은?"),
        )

    def test_next_week_resolves_to_next_monday_range(self):
        resolver = DateResolver(
            today_provider=lambda: date(2026, 7, 30)
        )

        resolved = resolver.resolve("What about next week?")

        self.assertEqual("next_week", resolved.kind)
        self.assertEqual("2026-08-03", resolved.start_date)
        self.assertEqual("2026-08-09", resolved.end_date)

    def test_goal_semantic_layer_exposes_common_follow_up_slots(self):
        context = build_semantic_context(
            "And tomorrow?",
            None,
            IntentContext(current_date="2026-07-30"),
        )

        self.assertTrue(context.slots["is_follow_up"].value)
        self.assertEqual(
            "en", context.slots["follow_up_language"].value
        )
        self.assertEqual(
            "and", context.slots["follow_up_phrase"].value
        )
        self.assertEqual("2026-07-31", context.temporal.date)


if __name__ == "__main__":
    unittest.main()
