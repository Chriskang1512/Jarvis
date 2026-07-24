import unittest
from types import SimpleNamespace

from jarvis.abilities.native.mail import MailAbility
from jarvis.abilities.native.mail.parser import MailIntentParser
from jarvis.abilities.native.mail.result import MailMessage, MailResult, MailSendResult
from jarvis.voice import VoicePipeline
from jarvis.voice.conversation import create_conversation_session
from jarvis.abilities import AbilityRegistry
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.tools import ToolRegistry


class TestMailSendAbility(unittest.TestCase):
    def test_planner_routes_send_and_reply_actions(self):
        ability_registry = AbilityRegistry()
        ability_registry.register(MailAbility(provider=FakeSendProvider()))
        registry = ToolRegistry()
        ability_registry.register_tools(registry)
        dispatcher = RuntimeToolDispatcher(registry)

        send_plan = dispatcher.create_plan("아야에게 테스트 메일 보내줘")
        reply_plan = dispatcher.create_plan("그 메일에 확인했다고 답장해줘")

        self.assertEqual(send_plan.steps[0].tool_name, "mail")
        self.assertEqual(send_plan.steps[0].action, "send")
        self.assertEqual(reply_plan.steps[0].tool_name, "mail")
        self.assertEqual(reply_plan.steps[0].action, "reply")

    def test_compose_parser_builds_predictable_draft(self):
        query = MailIntentParser().parse("아야에게 내일 오후 3시에 만나자고 메일 보내줘")

        self.assertEqual(query.action, "send")
        self.assertEqual(query.recipient_name, "아야")
        self.assertEqual(query.subject, "내일 일정 안내")
        self.assertEqual(query.body, "내일 오후 3시에 만나요.")

    def test_direct_address_requires_confirmation_without_provider_call(self):
        provider = FakeSendProvider()
        ability = MailAbility(provider=provider)

        result = ability.execute({"text": "test@example.com으로 테스트 메일 보내줘"})

        self.assertTrue(result.success)
        self.assertTrue(result.data.requires_confirmation)
        self.assertEqual(result.metadata["permission"], "confirm_required")
        self.assertEqual(provider.send_calls, [])
        self.assertTrue(result.metadata["query"].pending_action_id)

    def test_confirmed_send_uses_exact_previewed_draft(self):
        provider = FakeSendProvider()
        ability = MailAbility(provider=provider)
        preview = ability.execute({"text": "test@example.com으로 테스트 메일 보내줘"})
        input_data = preview.metadata["query"].to_input_data()
        input_data["_confirmed"] = True

        result = ability.execute(input_data)

        self.assertTrue(result.success)
        self.assertEqual(len(provider.send_calls), 1)
        outgoing = provider.send_calls[0]
        self.assertEqual(outgoing.to, ("test@example.com",))
        self.assertEqual(outgoing.subject, "테스트 메일")
        self.assertEqual(outgoing.body, "테스트 메일입니다.")

    def test_duplicate_confirmed_send_is_blocked(self):
        provider = FakeSendProvider()
        ability = MailAbility(provider=provider)
        preview = ability.execute({"text": "test@example.com으로 테스트 메일 보내줘"})
        input_data = preview.metadata["query"].to_input_data()
        input_data["_confirmed"] = True

        first = ability.execute(input_data)
        second = ability.execute(input_data)

        self.assertTrue(first.success)
        self.assertFalse(second.success)
        self.assertEqual(second.data.error_code, "DUPLICATE_SEND_BLOCKED")
        self.assertEqual(len(provider.send_calls), 1)

    def test_contact_recipient_exact_match_uses_contact_email(self):
        provider = FakeSendProvider()
        contacts = FakeContactsProvider(contact=contact("아야", ["aya@example.com"]))
        ability = MailAbility(provider=provider, contacts_provider=contacts)

        result = ability.execute({"text": "아야에게 테스트 메일 보내줘"})

        self.assertTrue(result.success)
        self.assertEqual(result.metadata["query"].to, ("aya@example.com",))
        self.assertEqual(result.metadata["query"].recipient_name, "아야")

    def test_contact_without_email_is_blocked(self):
        ability = MailAbility(
            provider=FakeSendProvider(),
            contacts_provider=FakeContactsProvider(contact=contact("아야", [])),
        )

        result = ability.execute({"text": "아야에게 테스트 메일 보내줘"})

        self.assertFalse(result.success)
        self.assertEqual(result.data.error_code, "RECIPIENT_EMAIL_MISSING")
        self.assertIn("이메일 주소가 없습니다", result.error)

    def test_ambiguous_contact_is_blocked(self):
        ability = MailAbility(
            provider=FakeSendProvider(),
            contacts_provider=FakeContactsProvider(error_code="contact_ambiguous"),
        )

        result = ability.execute({"text": "아야에게 테스트 메일 보내줘"})

        self.assertFalse(result.success)
        self.assertEqual(result.data.error_code, "AMBIGUOUS_RECIPIENT")

    def test_invalid_direct_email_is_blocked(self):
        ability = MailAbility(provider=FakeSendProvider())

        result = ability.execute(
            {
                "action": "send",
                "to": ["bad-address"],
                "subject": "테스트",
                "body": "본문",
                "_confirmed": True,
            }
        )

        self.assertFalse(result.success)
        self.assertEqual(result.data.error_code, "INVALID_EMAIL_ADDRESS")

    def test_reply_uses_last_selected_message_context(self):
        message = MailMessage(
            id="m1",
            thread_id="t1",
            sender_name="아야",
            sender_email="aya@example.com",
            subject="내일 일정",
            rfc_message_id="<source@example.com>",
        )
        provider = FakeSendProvider(messages=(message,))
        ability = MailAbility(provider=provider)
        ability.execute({"action": "list"})
        ability.execute({"action": "get", "ordinal": 1})

        preview = ability.execute({"text": "그 메일에 확인했다고 답장해줘"})

        query = preview.metadata["query"]
        self.assertEqual(query.action, "reply")
        self.assertEqual(query.reply_to_message_id, "m1")
        self.assertEqual(query.thread_id, "t1")
        self.assertEqual(query.to, ("aya@example.com",))
        self.assertEqual(query.body, "확인했습니다.")
        self.assertEqual(query.subject, "Re: 내일 일정")

    def test_reply_without_context_is_blocked(self):
        ability = MailAbility(provider=FakeSendProvider())

        result = ability.execute({"text": "그 메일에 확인했다고 답장해줘"})

        self.assertFalse(result.success)
        self.assertEqual(result.data.error_code, "REPLY_TARGET_NOT_FOUND")

    def test_voice_cancellation_clears_pending_without_send(self):
        provider = FakeSendProvider()
        ability = MailAbility(provider=provider)
        preview = ability.execute({"text": "test@example.com으로 테스트 메일 보내줘"})
        query = preview.metadata["query"]
        session = create_conversation_session(follow_up_timeout=10)
        session.start()
        session.set_pending_action(
            {
                "ability": "mail",
                "action": "send",
                "input_data": query.to_input_data(),
            }
        )
        pipeline = VoicePipeline(
            wake_listener=None,
            stt_provider=None,
            chat_service=None,
            tts_provider=None,
            conversation_session=session,
        )

        reply = pipeline.try_pending_action_confirmation_reply("아니")

        self.assertEqual(reply, "취소했습니다.")
        self.assertIsNone(session.get_pending_action())
        self.assertEqual(provider.send_calls, [])


class FakeSendProvider:
    provider_name = "fake_mail"

    def __init__(self, messages=()):
        self.messages = tuple(messages)
        self.send_calls = []
        self.reply_calls = []

    def list_messages(self, query):
        return MailResult(
            success=True,
            action="list",
            messages=self.messages,
            message_count=len(self.messages),
            provider=self.provider_name,
        )

    def search_messages(self, query):
        return self.list_messages(query)

    def get_message(self, message_id):
        message = next((item for item in self.messages if item.id == message_id), None)
        return MailResult(
            success=message is not None,
            action="get",
            message=message,
            messages=(message,) if message else (),
            message_count=1 if message else 0,
            provider=self.provider_name,
        )

    def send_message(self, outgoing):
        self.send_calls.append(outgoing)
        return MailSendResult(
            success=True,
            action="send",
            message_id="sent-1",
            thread_id="thread-1",
            recipient=outgoing.to[0],
            recipient_name=outgoing.recipient_name,
            subject=outgoing.subject,
            verified=True,
            provider=self.provider_name,
        )

    def reply_message(self, outgoing):
        self.reply_calls.append(outgoing)
        return MailSendResult(
            success=True,
            action="reply",
            message_id="reply-1",
            thread_id=outgoing.thread_id,
            recipient=outgoing.to[0],
            recipient_name=outgoing.recipient_name,
            subject=outgoing.subject,
            verified=True,
            provider=self.provider_name,
        )


class FakeContactsProvider:
    def __init__(self, contact=None, error_code=""):
        self.contact = contact
        self.error_code = error_code

    def get_contact(self, query):
        return SimpleNamespace(
            success=self.contact is not None and not self.error_code,
            contact=self.contact,
            contacts=(),
            error_code=self.error_code,
        )


def contact(name, emails):
    return SimpleNamespace(display_name=name, emails=tuple(emails), aliases=())


if __name__ == "__main__":
    unittest.main()
