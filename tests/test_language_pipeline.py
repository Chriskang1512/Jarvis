import unittest
from unittest.mock import patch

from jarvis.config.settings import JarvisConfig, LanguageConfig
from jarvis.runtime import (
    LanguageControlAction,
    LanguageControlCommandParser,
    LanguageContext,
    LanguagePolicy,
    LanguageResolver,
    RuntimeTurn,
    TurnOwner,
)
from jarvis.runtime.language import detect_language
from jarvis.voice.pipeline import VoicePipeline
from voice_main import get_stt_openai_language


class RecordingChat:
    def __init__(self, response="日本語の返答です。"):
        self.response = response
        self.requests = []

    def generate_reply(self, text):
        self.requests.append(text)
        return self.response


class RecordingTTS:
    def __init__(self):
        self.voice = "alloy"
        self.streaming_enabled = False
        self.calls = []

    def speak(self, text):
        self.calls.append((self.voice, text))


class RecordingOpenAISTT:
    def __init__(self):
        self.language = "auto"

    def listen(self):
        return ""


class TestLanguagePipeline(unittest.TestCase):
    def test_language_control_parser_recognizes_mode_exit_variants(self):
        parser = LanguageControlCommandParser()
        phrases = (
            "\uc774\uc81c \uc6d0\ub798 \ubaa8\ub4dc\ub85c \ub3cc\uc544\uc640.",
            "\uc6d0\ub798\ub300\ub85c \ub3cc\uc544\uc640",
            "\uae30\ubcf8\uc73c\ub85c \ub3cc\uc544\uac00",
            "\uc774\uc81c \uc77c\ubc18 \ubaa8\ub4dc\ub85c \ub3cc\uc544\uc640.",
            "\uc790\ub3d9\uc73c\ub85c \ud574",
            "\uc5b8\uc5b4 \uace0\uc815 \ud574\uc81c",
            "\u65e5\u672c\u8a9e\u30e2\u30fc\u30c9\u89e3\u9664",
            "English mode off",
        )

        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    parser.parse(phrase).action,
                    LanguageControlAction.CLEAR_OVERRIDE,
                )

    @patch("jarvis.runtime.language.trace_event")
    def test_original_mode_command_clears_override_and_returns_to_auto(
        self,
        trace,
    ):
        resolver = LanguageResolver()
        resolver.resolve(
            "\u4eca\u304b\u3089\u65e5\u672c\u8a9e\u3067\u8a71\u305d\u3046.",
            conversation_id="CONV-EXIT",
        )

        restored = resolver.resolve(
            "\uc774\uc81c \uc6d0\ub798 \ubaa8\ub4dc\ub85c \ub3cc\uc544\uc640.",
            conversation_id="CONV-EXIT",
        )
        follow_up = resolver.resolve(
            "\uc9c0\uae08 \ub0a0\uc528 \uc5b4\ub54c?",
            conversation_id="CONV-EXIT",
        )

        self.assertTrue(restored.override_cleared)
        self.assertFalse(restored.conversation_override)
        self.assertEqual(restored.response_language, "ko")
        self.assertFalse(follow_up.conversation_override)
        self.assertEqual(follow_up.response_language, "ko")
        trace.assert_any_call(
            "runtime.language.override_cleared",
            conversation_id="CONV-EXIT",
            detected_language="ko",
            previous_language="ja",
            previous="ja",
            previous_conversation_language="ja",
            conversation_language="ko",
            response_language="ko",
            response_source="explicit_control",
            override_cleared=True,
            current="AUTO",
        )

    def test_language_control_parser_recognizes_clear_override_phrases(self):
        parser = LanguageControlCommandParser()
        phrases = (
            "이제 자동으로 돌아가",
            "언어 자동으로 돌아가",
            "자동 언어로 돌아가",
            "자동 감지로 돌아가",
            "입력 언어에 맞춰 대답해",
            "언어 설정 초기화해",
            "언어 고정 해제해",
            "기본 언어 모드로 돌아가",
            "Switch back to automatic language mode",
            "Use the language I speak",
            "Clear the language override",
            "じどう げんご もーど に もどして",
            "自動言語モードに戻して",
            "지도- 겐고 모-도니 모도시테",
            "자동 언어 모드로 돌아가 줘",
        )

        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    parser.parse(phrase).action,
                    LanguageControlAction.CLEAR_OVERRIDE,
                )

    def test_runtime_banner_uses_effective_auto_stt_language(self):
        config = JarvisConfig(language=LanguageConfig(policy="AUTO"))

        with patch.dict("os.environ", {}, clear=True), patch(
            "voice_main.read_env_file_value",
            return_value="",
        ):
            self.assertEqual(get_stt_openai_language(config), "auto")

    def test_force_language_sets_effective_stt_hint(self):
        config = JarvisConfig(language=LanguageConfig(policy="FORCE_JA"))

        with patch.dict("os.environ", {}, clear=True), patch(
            "voice_main.read_env_file_value",
            return_value="",
        ):
            self.assertEqual(get_stt_openai_language(config), "ja")

    def test_detects_korean_japanese_and_english(self):
        self.assertEqual(detect_language("내일 날씨 알려줘")[0], "ko")
        self.assertEqual(detect_language("あしたの天気を教えて")[0], "ja")
        self.assertEqual(detect_language("What's the weather tomorrow?")[0], "en")

    def test_mixed_language_detection_excludes_named_location_entities(self):
        self.assertEqual(detect_language("\uc624\uc0ac\uce74\u306e\u5929\u6c17\u306f\uff1f")[0], "ja")
        self.assertEqual(detect_language("\uc11c\uc6b8 weather")[0], "en")
        self.assertEqual(detect_language("\uc624\uc0ac\uce74 weather")[0], "en")
        self.assertEqual(detect_language("\uc624\uc0ac\uce74 \ub0a0\uc528")[0], "ko")

    def test_detects_japanese_returned_as_hangul_phonetics(self):
        language, confidence = detect_language(
            "트와이스의 오스스메 노 쿄쿠 아루?"
        )

        self.assertEqual(language, "ja")
        self.assertGreaterEqual(confidence, 0.85)

    def test_hangul_phonetic_detection_does_not_override_normal_korean(self):
        self.assertEqual(
            detect_language("트와이스의 추천곡은 있어?")[0],
            "ko",
        )

    def test_detects_english_returned_as_hangul_phonetics(self):
        language, confidence = detect_language(
            "아니송 두유노 어 트와이스?"
        )

        self.assertEqual(language, "en")
        self.assertGreaterEqual(confidence, 0.85)

    def test_hangul_english_detection_does_not_override_normal_korean(self):
        self.assertEqual(
            detect_language("내일 트와이스 노래 추천해 줘")[0],
            "ko",
        )

    def test_auto_policy_follows_input_language(self):
        resolver = LanguageResolver()

        context = resolver.resolve(
            "あしたの天気を教えて",
            conversation_id="CONV-1",
            stt_provider="openai",
        )

        self.assertEqual(context.detected_language, "ja")
        self.assertEqual(context.response_language, "ja")
        self.assertEqual(context.tts_voice, "openai:nova:ja")

    def test_follow_up_preserves_conversation_language_across_code_switch(self):
        resolver = LanguageResolver()
        initial = resolver.resolve(
            "\u5927\u962a\u306e\u5929\u6c17\u306f\uff1f",
            conversation_id="CONV-CODE-SWITCH",
        )
        follow_up = resolver.resolve(
            "How about tomorrow?",
            conversation_id="CONV-CODE-SWITCH",
            preserve_conversation=True,
        )

        self.assertEqual(initial.conversation_language, "ja")
        self.assertEqual(follow_up.detected_language, "en")
        self.assertEqual(follow_up.conversation_language, "ja")
        self.assertEqual(follow_up.response_language, "ja")
        self.assertEqual(follow_up.response_source, "conversation_continuity")

    def test_new_non_follow_up_updates_conversation_language(self):
        resolver = LanguageResolver()
        resolver.resolve(
            "\u5927\u962a\u306e\u5929\u6c17\u306f\uff1f",
            conversation_id="CONV-NEW-TURN",
        )

        context = resolver.resolve(
            "Tell me about London.",
            conversation_id="CONV-NEW-TURN",
            preserve_conversation=False,
        )

        self.assertEqual(context.conversation_language, "en")
        self.assertEqual(context.response_language, "en")

    def test_general_mode_command_clears_conversation_continuity(self):
        resolver = LanguageResolver()
        resolver.resolve(
            "\u5927\u962a\u306e\u5929\u6c17\u306f\uff1f",
            conversation_id="CONV-GENERAL-MODE",
        )

        restored = resolver.resolve(
            "\uc774\uc81c \uc77c\ubc18 \ubaa8\ub4dc\ub85c \ub3cc\uc544\uc640.",
            conversation_id="CONV-GENERAL-MODE",
            preserve_conversation=True,
        )

        self.assertTrue(restored.override_cleared)
        self.assertEqual(restored.detected_language, "ko")
        self.assertEqual(restored.conversation_language, "ko")
        self.assertEqual(restored.response_language, "ko")
        self.assertEqual(restored.response_source, "explicit_control")

    def test_general_mode_command_resets_forced_policy_to_auto(self):
        resolver = LanguageResolver(LanguagePolicy.FORCE_JA)

        restored = resolver.resolve(
            "\uc774\uc81c \uc77c\ubc18 \ubaa8\ub4dc\ub85c \ub3cc\uc544\uc640.",
            conversation_id="CONV-FORCED-GENERAL",
            preserve_conversation=True,
        )
        japanese = resolver.resolve(
            "\u660e\u65e5\u306e\u5929\u6c17\u306f\uff1f",
            conversation_id="CONV-FORCED-GENERAL",
        )
        english = resolver.resolve(
            "How is the weather today?",
            conversation_id="CONV-FORCED-GENERAL",
        )

        self.assertEqual(restored.policy, LanguagePolicy.AUTO)
        self.assertEqual(restored.response_language, "ko")
        self.assertEqual(japanese.response_language, "ja")
        self.assertEqual(english.response_language, "en")

    def test_conversation_override_survives_korean_follow_up(self):
        resolver = LanguageResolver()
        resolver.resolve("오늘 일본어로만 대화하자", conversation_id="CONV-1")

        context = resolver.resolve("내일 날씨 알려줘", conversation_id="CONV-1")

        self.assertEqual(context.detected_language, "ko")
        self.assertEqual(context.response_language, "ja")
        self.assertTrue(context.conversation_override)

    def test_from_now_response_language_command_persists_for_follow_up(self):
        resolver = LanguageResolver()

        initial = resolver.resolve(
            "\uc9c0\uae08\ubd80\ud130 \uc77c\ubcf8\uc5b4\ub85c \ub2f5\ud574.",
            conversation_id="CONV-1",
        )
        follow_up = resolver.resolve(
            "\ub0b4\uc77c \uc624\uc0ac\uce74 \ub0a0\uc528 \uc5b4\ub54c?",
            conversation_id="CONV-1",
        )

        self.assertEqual(initial.response_language, "ja")
        self.assertEqual(follow_up.detected_language, "ko")
        self.assertEqual(follow_up.response_language, "ja")
        self.assertTrue(follow_up.conversation_override)

    def test_auto_command_clears_conversation_override(self):
        resolver = LanguageResolver()
        resolver.resolve("영어로만 대화하자", conversation_id="CONV-1")

        restored = resolver.resolve(
            "이제 자동으로 돌아가",
            conversation_id="CONV-1",
        )
        follow_up = resolver.resolve(
            "明日の天気は？",
            conversation_id="CONV-1",
        )

        self.assertTrue(restored.override_cleared)
        self.assertEqual(restored.response_language, "ko")
        self.assertFalse(restored.conversation_override)
        self.assertEqual(follow_up.response_language, "ja")
        self.assertFalse(follow_up.conversation_override)

    def test_language_named_auto_command_clears_override(self):
        resolver = LanguageResolver()
        resolver.resolve("일본어로만 대화하자", conversation_id="CONV-1")

        restored = resolver.resolve(
            "이제 언어 자동으로 돌아가",
            conversation_id="CONV-1",
        )

        self.assertTrue(restored.override_cleared)
        self.assertEqual(restored.response_language, "ko")

    def test_force_policy_wins_over_detected_language(self):
        resolver = LanguageResolver(LanguagePolicy.FORCE_EN)

        context = resolver.resolve("내일 날씨 알려줘")

        self.assertEqual(context.detected_language, "ko")
        self.assertEqual(context.response_language, "en")

    def test_conversation_override_is_applied_to_next_openai_stt_request(self):
        stt = RecordingOpenAISTT()
        pipeline = VoicePipeline(None, stt, None, None)
        pipeline.voice_session = type("VoiceSession", (), {"session_id": "CONV-STT"})()
        pipeline.language_resolver.resolve(
            "\uc9c0\uae08\ubd80\ud130 \uc77c\ubcf8\uc5b4\ub85c \ub2f5\ud574.",
            conversation_id="CONV-STT",
        )

        selected = pipeline.configure_stt_language_hint()

        self.assertEqual(selected, "ja")
        self.assertEqual(stt.language, "ja")

    def test_auto_mode_restores_openai_stt_auto_detection(self):
        stt = RecordingOpenAISTT()
        stt.language = "ja"
        pipeline = VoicePipeline(None, stt, None, None)
        pipeline.voice_session = type("VoiceSession", (), {"session_id": "CONV-AUTO"})()

        selected = pipeline.configure_stt_language_hint()

        self.assertEqual(selected, "auto")
        self.assertEqual(stt.language, "auto")

    def test_forced_language_is_used_as_stt_hint(self):
        resolver = LanguageResolver(LanguagePolicy.FORCE_EN)

        self.assertEqual(resolver.stt_language_hint("CONV-1"), "en")

    def test_runtime_turn_snapshot_contains_language_context(self):
        turn = RuntimeTurn(
            owner=TurnOwner.VOICE,
            language_context=LanguageContext(
                detected_language="ja",
                response_language="ja",
                tts_voice="openai:nova:ja",
                stt_provider="openai",
                confidence=0.99,
            ),
        )

        self.assertEqual(
            turn.snapshot()["language_context"]["response_language"],
            "ja",
        )

    def test_pipeline_translates_tool_response_and_selects_tts_voice(self):
        chat = RecordingChat()
        tts = RecordingTTS()
        pipeline = VoicePipeline(None, None, chat, tts)
        pipeline.resolve_language_context("あしたの天気を教えて")

        translated = pipeline.ensure_response_language("내일은 맑습니다.")
        pipeline.speak_reply(translated)

        self.assertEqual(translated, "日本語の返答です。")
        self.assertEqual(tts.calls[0][0], "nova")
        self.assertEqual(tts.voice, "alloy")


    def test_korean_response_policy_normalizes_japanese_llm_output(self):
        chat = RecordingChat(response="\ud55c\uad6d\uc5b4 \uc751\ub2f5")
        pipeline = VoicePipeline(None, None, chat, None)
        pipeline.language_context = LanguageContext(
            detected_language="ko",
            conversation_language="ko",
            response_language="ko",
            tts_voice="openai:alloy:ko",
        )

        normalized = pipeline.ensure_response_language(
            "\u7279\u306b\u4f55\u3082\u3057\u3066\u3044\u307e\u305b\u3093\u3002"
        )

        self.assertEqual(normalized, "\ud55c\uad6d\uc5b4 \uc751\ub2f5")
        self.assertEqual(len(chat.requests), 1)
        self.assertIn("Respond in Korean.", chat.requests[0])

    def test_korean_language_aware_prompt_is_explicit(self):
        pipeline = VoicePipeline(None, None, None, None)
        pipeline.language_context = LanguageContext(
            detected_language="ko",
            conversation_language="ko",
            response_language="ko",
        )

        prompt = pipeline.language_aware_prompt("\ubb50 \ud558\uace0 \uc788\uc5b4?")

        self.assertIn("Respond in Korean.", prompt)
        self.assertIn("\ubb50 \ud558\uace0 \uc788\uc5b4?", prompt)

    @patch("jarvis.voice.pipeline.trace_event")
    def test_final_tts_guard_normalizes_mismatched_response(self, trace):
        chat = RecordingChat(response="\ud55c\uad6d\uc5b4 \uc751\ub2f5")
        tts = RecordingTTS()
        pipeline = VoicePipeline(None, None, chat, tts)
        pipeline.language_context = LanguageContext(
            detected_language="ko",
            conversation_language="ko",
            response_language="ko",
            tts_voice="openai:alloy:ko",
        )

        pipeline.speak_reply(
            "\u7279\u306b\u4f55\u3082\u3057\u3066\u3044\u307e\u305b\u3093\u3002"
        )

        self.assertEqual(tts.calls[0][1], "\ud55c\uad6d\uc5b4 \uc751\ub2f5")
        trace.assert_any_call(
            "runtime.language.response_mismatch",
            expected="ko",
            actual="ja",
            source="final_tts_guard",
            tts_voice="openai:alloy:ko",
        )
        trace.assert_any_call(
            "runtime.language.response_normalized",
            from_language="ja",
            to_language="ko",
            source="final_tts_guard",
            tts_voice="openai:alloy:ko",
        )

    def test_response_guard_ignores_language_neutral_iso_datetime(self):
        chat = RecordingChat()
        pipeline = VoicePipeline(None, None, chat, None)
        pipeline.language_context = LanguageContext(
            detected_language="ko",
            conversation_language="ko",
            response_language="ko",
        )

        response = pipeline.ensure_response_language(
            "2026-07-28T20:43:43",
            source="ability_formatter",
        )

        self.assertEqual(response, "2026-07-28T20:43:43")
        self.assertEqual(chat.requests, [])


if __name__ == "__main__":
    unittest.main()
