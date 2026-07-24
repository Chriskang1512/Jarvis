import unittest

from jarvis.voice.pipeline import (
    is_calendar_query_command_text,
    is_todo_like_failed_request,
    is_todo_ordinal_or_mutation_text,
    safe_tool_like_failed_request_reply,
)
from jarvis.voice.semantic import SemanticTranscriptContext, SemanticTranscriptNormalizer


class TodoVoiceRoutingTest(unittest.TestCase):
    def test_todo_completion_does_not_route_as_calendar_ordinal_followup(self):
        self.assertTrue(is_todo_ordinal_or_mutation_text("첫 번째 완료했어"))
        self.assertTrue(is_todo_ordinal_or_mutation_text("첫 번째 삭제해"))

    def test_plain_calendar_ordinal_can_still_route_to_calendar_followup(self):
        self.assertFalse(is_todo_ordinal_or_mutation_text("첫 번째는?"))

    def test_calendar_query_commands_are_not_ordinal_followups(self):
        self.assertTrue(is_calendar_query_command_text("\ub2e4\uc74c \uc8fc \uc77c\uc815 \uc54c\ub824\uc918"))
        self.assertTrue(is_calendar_query_command_text("\ub2e4\uc74c \uc77c\uc815 \uc54c\ub824\uc918"))
        self.assertFalse(is_calendar_query_command_text("\ub2e4\uc74c \uc77c\uc815\uc740?"))

    def test_semantic_corrects_todo_create_suffix_near_miss(self):
        normalizer = SemanticTranscriptNormalizer()

        result = normalizer.normalize(
            "\uc6b0\uc720 \uc0ac\uae30 \ucd95\ud558\ud574.",
            "\uc6b0\uc720 \uc0ac\uae30 \ucd95\ud558\ud574.",
            SemanticTranscriptContext(),
        )

        self.assertEqual(result.semantic_text, "\uc6b0\uc720 \uc0ac\uae30 \ucd94\uac00\ud574.")
        self.assertTrue(any(correction.reason == "todo_create_suffix_stt_near_miss" for correction in result.corrections))

    def test_todo_like_failure_is_not_sent_to_general_llm(self):
        self.assertTrue(is_todo_like_failed_request("\uc6b0\uc720 \uc0ac\uae30 \ucd95\ud558\ud574."))
        self.assertFalse(is_todo_like_failed_request("\ucd95\ud558\ud574."))

    def test_tool_like_mail_failure_gets_safe_clarification(self):
        reply = safe_tool_like_failed_request_reply("\ucd5c\uadfc \uc77c \uc54c\ub824\uc918")

        self.assertIsNotNone(reply)
        self.assertIn("\uba54\uc77c", reply)

    def test_tool_like_current_info_failure_gets_safe_clarification(self):
        reply = safe_tool_like_failed_request_reply("\ucd5c\uc2e0 \ub274\uc2a4 \uc54c\ub824\uc918")

        self.assertIsNotNone(reply)
        self.assertIn("\ud655\uc778", reply)

    def test_plain_chat_can_still_use_general_llm(self):
        self.assertIsNone(safe_tool_like_failed_request_reply("\uc548\ub155"))


if __name__ == "__main__":
    unittest.main()
