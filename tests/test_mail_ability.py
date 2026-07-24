import unittest
from datetime import datetime, time

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.mail import MailAbility
from jarvis.abilities.native.mail.result import MailMessage, MailResult
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.tools import ToolRegistry, ToolRequest


class TestMailAbilityVerticalSlice(unittest.TestCase):
    def setUp(self):
        self.provider = FakeMailProvider()
        ability_registry = AbilityRegistry()
        ability_registry.register(MailAbility(provider=self.provider))
        self.tool_registry = ToolRegistry()
        ability_registry.register_tools(self.tool_registry)
        self.dispatcher = RuntimeToolDispatcher(self.tool_registry)

    def test_planner_routes_recent_mail_to_mail_list(self):
        plan = self.dispatcher.create_plan("최근 메일 알려줘")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "mail")
        self.assertEqual(plan.steps[0].action, "list")

    def test_planner_routes_recent_email_to_mail_before_contacts(self):
        plan = self.dispatcher.create_plan("최근 이메일 알려줘")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "mail")
        self.assertEqual(plan.steps[0].action, "list")

    def test_planner_routes_unread_mail_to_mail_search(self):
        plan = self.dispatcher.create_plan("안 읽은 메일 알려줘")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "mail")
        self.assertEqual(plan.steps[0].action, "search")

    def test_planner_routes_sender_mail_to_mail_search(self):
        plan = self.dispatcher.create_plan("GitHub 메일 알려줘")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "mail")
        self.assertEqual(plan.steps[0].action, "search")

    def test_planner_routes_keyword_mail_to_search_and_preserves_query(self):
        plan = self.dispatcher.create_plan("퇴근 메일 알려줘")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "mail")
        self.assertEqual(plan.steps[0].action, "search")

        result = self.dispatcher.execute(ToolRequest("mail", {"text": "퇴근 메일 알려줘"}))

        self.assertTrue(result.success)
        self.assertEqual(result.output.data.action, "search")
        self.assertEqual(result.output.data.query, "퇴근")

    def test_planner_recovers_common_mail_stt_variants(self):
        recent_plan = self.dispatcher.create_plan("최근 일 알려줘")
        keyword_plan = self.dispatcher.create_plan("퇴근 매일 알려줘")

        self.assertEqual(recent_plan.step_count, 1)
        self.assertEqual(recent_plan.steps[0].tool_name, "mail")
        self.assertEqual(recent_plan.steps[0].action, "list")
        self.assertEqual(keyword_plan.step_count, 1)
        self.assertEqual(keyword_plan.steps[0].tool_name, "mail")
        self.assertEqual(keyword_plan.steps[0].action, "search")

        result = self.dispatcher.execute(ToolRequest("mail", {"text": "퇴근 매일 알려줘"}))

        self.assertTrue(result.success)
        self.assertEqual(result.output.data.query, "퇴근")

    def test_mail_list_keeps_recent_messages_and_formatter_omits_body(self):
        result = self.dispatcher.execute(ToolRequest("mail", {"text": "최근 메일 알려줘"}))

        self.assertTrue(result.success)
        self.assertEqual(result.output.data.provider, "fake_mail")
        self.assertEqual(result.output.data.message_count, 2)
        self.assertIn("최근 메일은 2건입니다.", result.output.to_natural_language())
        self.assertIn("1. GitHub. Pull Request 리뷰 요청.", result.output.to_natural_language())
        self.assertIn("오늘 오후 5시 25분", result.output.to_natural_language())
        self.assertNotIn("body-1", result.output.to_natural_language())

    def test_mail_ordinal_get_reads_selected_summary(self):
        self.dispatcher.execute(ToolRequest("mail", {"text": "최근 메일 알려줘"}))

        result = self.dispatcher.execute(ToolRequest("mail", {"text": "2번 읽어줘"}))

        self.assertTrue(result.success)
        self.assertEqual(self.provider.get_ids, ["m2"])
        self.assertIn("OpenAI의 메일입니다.", result.output.to_natural_language())
        self.assertIn("제목은 API 업데이트입니다.", result.output.to_natural_language())
        self.assertIn("body-2", result.output.to_natural_language())

    def test_mail_this_one_followup_routes_to_first_message(self):
        plan = self.dispatcher.create_plan("이번 읽어줘")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "mail")
        self.assertEqual(plan.steps[0].action, "get")


class FakeMailProvider:
    provider_name = "fake_mail"

    def __init__(self):
        today = datetime.now().date()
        self.messages = (
            MailMessage(
                id="m1",
                thread_id="t1",
                sender_name="GitHub",
                subject="Pull Request 리뷰 요청",
                received_at=str(int(datetime.combine(today, time(17, 25)).timestamp() * 1000)),
                body_summary="body-1",
            ),
            MailMessage(
                id="m2",
                thread_id="t2",
                sender_name="OpenAI",
                subject="API 업데이트",
                received_at=str(int(datetime.combine(today, time(17, 30)).timestamp() * 1000)),
                body_summary="body-2",
            ),
        )
        self.get_ids = []

    def list_messages(self, query):
        return MailResult(success=True, action="list", messages=self.messages, message_count=len(self.messages), query=query.query)

    def search_messages(self, query):
        return MailResult(success=True, action="search", messages=self.messages[:1], message_count=1, query=query.query)

    def get_message(self, message_id):
        self.get_ids.append(message_id)
        for message in self.messages:
            if message.id == message_id:
                return MailResult(success=True, action="get", message=message, messages=(message,), message_count=1)
        return MailResult(success=False, action="get", error_code="MAIL_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
