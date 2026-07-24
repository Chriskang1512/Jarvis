import unittest
from types import SimpleNamespace

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.calendar import CalendarAbility, CalendarEvent, MockCalendarProvider
from jarvis.abilities.native.contacts import ContactAbility
from jarvis.abilities.native.mail import MailAbility
from jarvis.abilities.native.mail.result import MailResult, MailSendResult
from jarvis.core.contacts import ContactRepository, InMemoryContactStorage
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.tools import ToolRegistry


class TestWorkspaceIntegration(unittest.TestCase):
    def test_planner_builds_contacts_then_mail_plan(self):
        dispatcher, _, _ = create_dispatcher()

        plan = dispatcher.create_plan("우수 연락처 찾아서 테스트 메일 보내줘")

        self.assertEqual([step.tool_name for step in plan.steps], ["contacts", "mail"])
        self.assertEqual(plan.steps[1].depends_on, (1,))

    def test_contact_email_is_frozen_into_mail_preview(self):
        dispatcher, repository, provider = create_dispatcher()
        repository.ensure("우수", emails=("woosoo@example.com",))

        result = dispatcher.execute_plan_text("우수 연락처 찾아서 테스트 메일 보내줘")

        self.assertEqual(result.error, "confirm_required")
        query = result.step_results[-1].tool_result.output.metadata["query"]
        self.assertEqual(query.to, ("woosoo@example.com",))
        self.assertEqual(query.recipient_name, "우수")
        self.assertEqual(query.subject, "테스트 메일")
        self.assertEqual(provider.send_calls, [])

    def test_planner_builds_calendar_then_mail_plan(self):
        dispatcher, _, _ = create_dispatcher()

        plan = dispatcher.create_plan("아야에게 내일 오후 3시 일정 메일로 보내줘")

        self.assertEqual([step.tool_name for step in plan.steps], ["calendar", "mail"])
        self.assertEqual(plan.steps[1].depends_on, (1,))

    def test_calendar_event_is_frozen_into_mail_preview(self):
        event = CalendarEvent(id="event-1", title="제품 회의", date="2026-07-25", time="15:00")
        dispatcher, _, provider = create_dispatcher(events=[event])

        result = dispatcher.execute_plan_text("아야에게 내일 오후 3시 일정 메일로 보내줘")

        self.assertEqual(result.error, "confirm_required")
        query = result.step_results[-1].tool_result.output.metadata["query"]
        self.assertEqual(query.subject, "제품 회의 일정 안내")
        self.assertEqual(query.body, "2026-07-25 15:00 제품 회의 일정입니다.")
        self.assertEqual(provider.send_calls, [])

    def test_missing_calendar_event_never_reaches_send_confirmation(self):
        dispatcher, _, provider = create_dispatcher(events=[])

        result = dispatcher.execute_plan_text("아야에게 내일 오후 3시 일정 메일로 보내줘")

        self.assertNotEqual(result.error, "confirm_required")
        self.assertIn("메일 본문이 필요합니다", result.response)
        self.assertEqual(provider.send_calls, [])


class FakeMailProvider:
    provider_name = "fake_mail"

    def __init__(self):
        self.send_calls = []

    def list_messages(self, query):
        return MailResult(success=True, action="list", provider=self.provider_name)

    def search_messages(self, query):
        return self.list_messages(query)

    def send_message(self, outgoing):
        self.send_calls.append(outgoing)
        return MailSendResult(
            success=True,
            message_id="sent-1",
            thread_id="thread-1",
            recipient=outgoing.to[0],
            recipient_name=outgoing.recipient_name,
            subject=outgoing.subject,
            verified=True,
        )


class FakeContactsProvider:
    def get_contact(self, query):
        contact = SimpleNamespace(display_name="아야", emails=("aya@example.com",))
        return SimpleNamespace(success=True, contact=contact, error_code="")


def create_dispatcher(events=None):
    repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)
    mail_provider = FakeMailProvider()
    abilities = AbilityRegistry()
    abilities.register(ContactAbility(repository=repository))
    abilities.register(CalendarAbility(provider=MockCalendarProvider(events=list(events or []))))
    abilities.register(MailAbility(provider=mail_provider, contacts_provider=FakeContactsProvider()))
    tools = ToolRegistry()
    abilities.register_tools(tools)
    return RuntimeToolDispatcher(tools), repository, mail_provider


if __name__ == "__main__":
    unittest.main()
