import base64
from email import policy
from email.parser import BytesParser
import unittest
from unittest.mock import patch

from jarvis.abilities.native.mail import MailQuery
from jarvis.abilities.native.mail.result import OutgoingMail
from jarvis.providers.google.config import GoogleProviderConfig
from jarvis.providers.google.context import GoogleProviderContext
from jarvis.providers.google.error_mapper import GoogleErrorMapper
from jarvis.providers.google.gmail import GoogleMailProvider
from jarvis.providers.google.request_executor import GoogleRequestExecutor


class TestGoogleGmailProvider(unittest.TestCase):
    def test_google_gmail_search_hydrates_messages(self):
        service = FakeGmailService(
            list_response={"messages": [{"id": "m1", "threadId": "t1"}]},
            get_responses={
                "m1": gmail_message(
                    message_id="m1",
                    sender="GitHub <noreply@github.com>",
                    subject="Pull Request 리뷰 요청",
                    text="본문 내용입니다.",
                    labels=["UNREAD", "INBOX"],
                    filename="review.txt",
                )
            },
        )
        provider = GoogleMailProvider(client=service)

        result = provider.search_messages(MailQuery(action="search", query="from:github", limit=5))

        self.assertTrue(result.success)
        self.assertEqual(result.provider, "google_gmail")
        self.assertEqual(result.message_count, 1)
        self.assertEqual(result.messages[0].id, "m1")
        self.assertEqual(result.messages[0].sender_name, "GitHub")
        self.assertEqual(result.messages[0].sender_email, "noreply@github.com")
        self.assertEqual(result.messages[0].subject, "Pull Request 리뷰 요청")
        self.assertTrue(result.messages[0].unread)
        self.assertTrue(result.messages[0].has_attachment)
        self.assertEqual(result.messages[0].attachment_count, 1)
        self.assertEqual(result.messages[0].body_summary, "본문 내용입니다.")
        self.assertEqual(service.list_kwargs["q"], "-in:sent from:github")
        self.assertEqual(service.list_kwargs["labelIds"], ["INBOX"])
        self.assertEqual(service.list_kwargs["maxResults"], 5)

    def test_google_gmail_reuses_client_for_list_hydration(self):
        service = FakeGmailService(
            list_response={"messages": [{"id": "m1"}, {"id": "m2"}]},
            get_responses={
                "m1": gmail_message("m1", "GitHub <noreply@github.com>", "PR", "body 1"),
                "m2": gmail_message("m2", "OpenAI <news@openai.com>", "Update", "body 2"),
            },
        )
        client_factory = CountingClientFactory(service)
        context = GoogleProviderContext(
            config=GoogleProviderConfig(),
            auth_manager=object(),
            client_factory=client_factory,
            error_mapper=GoogleErrorMapper(),
            request_executor=GoogleRequestExecutor(),
        )
        provider = GoogleMailProvider(context=context)

        result = provider.search_messages(MailQuery(action="list", limit=5))

        self.assertTrue(result.success)
        self.assertEqual(result.message_count, 2)
        self.assertEqual(service.list_kwargs["q"], "-in:sent")
        self.assertEqual(service.list_kwargs["labelIds"], ["INBOX"])
        self.assertEqual(client_factory.calls, 1)

    def test_google_gmail_empty_search_returns_zero_messages(self):
        provider = GoogleMailProvider(client=FakeGmailService(list_response={}))

        result = provider.search_messages(MailQuery(action="search", query="is:unread"))

        self.assertTrue(result.success)
        self.assertEqual(result.message_count, 0)
        self.assertEqual(result.messages, ())

    def test_google_gmail_get_message_maps_single_message(self):
        service = FakeGmailService(
            get_responses={
                "m2": gmail_message(
                    message_id="m2",
                    sender="OpenAI <news@openai.com>",
                    subject="API 업데이트",
                    text="업데이트 요약입니다.",
                )
            }
        )
        provider = GoogleMailProvider(client=service)

        result = provider.get_message("m2")

        self.assertTrue(result.success)
        self.assertEqual(result.message.id, "m2")
        self.assertEqual(result.message.sender_name, "OpenAI")
        self.assertEqual(result.message.subject, "API 업데이트")
        self.assertEqual(result.message.body_summary, "업데이트 요약입니다.")

    def test_google_gmail_access_not_configured_uses_gmail_message(self):
        provider = GoogleMailProvider(client=FakeGmailService(error=FakeHttpError(403, "accessNotConfigured")))

        result = provider.search_messages(MailQuery(action="list"))

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "FEATURE_NOT_ENABLED")
        self.assertEqual(result.to_natural_language(), "Google Cloud에서 Gmail API를 활성화해야 합니다.")

    def test_google_gmail_send_builds_mime_and_verifies_metadata(self):
        service = FakeGmailService(
            send_response={"id": "sent-1", "threadId": "thread-1"},
            get_responses={
                "sent-1": gmail_message(
                    "sent-1",
                    "me@example.com",
                    "테스트 메일",
                    "",
                    to="test@example.com",
                )
            },
        )
        provider = GoogleMailProvider(client=service)
        outgoing = OutgoingMail(
            to=("test@example.com",),
            subject="테스트 메일",
            body="민감한 본문",
            pending_action_id="pending-1",
        )

        result = provider.send_message(outgoing)

        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertEqual(result.message_id, "sent-1")
        self.assertEqual(result.thread_id, "thread-1")
        raw = base64.urlsafe_b64decode(service.send_kwargs["body"]["raw"])
        message = BytesParser(policy=policy.default).parsebytes(raw)
        self.assertEqual(message["To"], "test@example.com")
        self.assertEqual(message["Subject"], "테스트 메일")
        self.assertEqual(message.get_content().strip(), "민감한 본문")
        self.assertEqual(service.get_kwargs[-1]["format"], "metadata")

    def test_google_gmail_reply_preserves_thread_and_reply_headers(self):
        service = FakeGmailService(
            send_response={"id": "reply-1", "threadId": "thread-1"},
            get_responses={
                "reply-1": gmail_message(
                    "reply-1",
                    "me@example.com",
                    "Re: 일정",
                    "",
                    to="aya@example.com",
                )
            },
        )
        provider = GoogleMailProvider(client=service)

        result = provider.reply_message(
            OutgoingMail(
                to=("aya@example.com",),
                subject="Re: 일정",
                body="확인했습니다.",
                reply_to_message_id="source-1",
                reply_to_header="<source@example.com>",
                thread_id="thread-1",
                pending_action_id="pending-2",
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(service.send_kwargs["body"]["threadId"], "thread-1")
        raw = base64.urlsafe_b64decode(service.send_kwargs["body"]["raw"])
        message = BytesParser(policy=policy.default).parsebytes(raw)
        self.assertEqual(message["In-Reply-To"], "<source@example.com>")
        self.assertEqual(message["References"], "<source@example.com>")

    def test_google_gmail_send_verification_mismatch_fails_with_message_id(self):
        service = FakeGmailService(
            send_response={"id": "sent-2", "threadId": "thread-2"},
            get_responses={
                "sent-2": gmail_message(
                    "sent-2",
                    "me@example.com",
                    "다른 제목",
                    "",
                    to="test@example.com",
                )
            },
        )
        provider = GoogleMailProvider(client=service)

        result = provider.send_message(
            OutgoingMail(
                to=("test@example.com",),
                subject="기대한 제목",
                body="본문",
                pending_action_id="pending-3",
            )
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "SEND_FAILED")
        self.assertEqual(result.message_id, "sent-2")

    def test_google_gmail_send_trace_masks_recipient_and_hashes_content(self):
        service = FakeGmailService(
            send_response={"id": "sent-3", "threadId": "thread-3"},
            get_responses={
                "sent-3": gmail_message(
                    "sent-3",
                    "me@example.com",
                    "비밀 제목",
                    "",
                    to="private@example.com",
                )
            },
        )
        provider = GoogleMailProvider(client=service)
        events = []

        with patch(
            "jarvis.providers.google.gmail.provider.trace_event",
            side_effect=lambda name, **payload: events.append((name, payload)),
        ):
            provider.send_message(
                OutgoingMail(
                    to=("private@example.com",),
                    subject="비밀 제목",
                    body="절대 로그에 남기면 안 되는 본문",
                    pending_action_id="pending-private",
                )
            )

        request_payload = next(payload for name, payload in events if name == "google_gmail.send.request")
        self.assertEqual(request_payload["to"], "p***@example.com")
        self.assertEqual(request_payload["body_length"], 18)
        self.assertNotIn("비밀 제목", str(request_payload))
        self.assertNotIn("절대 로그에 남기면 안 되는 본문", str(request_payload))


def gmail_message(message_id, sender, subject, text, labels=None, filename="", to=""):
    body_data = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")
    part = {"mimeType": "text/plain", "body": {"data": body_data}}
    if filename:
        part["filename"] = filename

    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "labelIds": labels or ["INBOX"],
        "snippet": text[:20],
        "internalDate": "1784700000000",
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
                {"name": "To", "value": to},
                {"name": "Message-ID", "value": f"<{message_id}@example.com>"},
            ],
            "parts": [part],
        },
    }


class FakeGmailService:
    def __init__(self, list_response=None, get_responses=None, error=None, send_response=None):
        self.list_response = list_response if list_response is not None else {"messages": []}
        self.get_responses = get_responses if get_responses is not None else {}
        self.error = error
        self.list_kwargs = None
        self.get_kwargs = []
        self.send_response = send_response or {}
        self.send_kwargs = None

    def users(self):
        return FakeUsersResource(self)


class CountingClientFactory:
    def __init__(self, service):
        self.service = service
        self.calls = 0

    def gmail_client(self):
        self.calls += 1
        return self.service


class FakeUsersResource:
    def __init__(self, service):
        self.service = service

    def messages(self):
        return FakeMessagesResource(self.service)


class FakeMessagesResource:
    def __init__(self, service):
        self.service = service

    def list(self, **kwargs):
        self.service.list_kwargs = kwargs
        return FakeRequest(self.service.list_response, self.service.error)

    def get(self, **kwargs):
        self.service.get_kwargs.append(kwargs)
        return FakeRequest(self.service.get_responses.get(kwargs.get("id"), {}), self.service.error)

    def send(self, **kwargs):
        self.service.send_kwargs = kwargs
        return FakeRequest(self.service.send_response, self.service.error)


class FakeRequest:
    def __init__(self, response, error=None):
        self.response = response
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.response


class FakeHttpError(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.resp = type("Resp", (), {"status": status})()


if __name__ == "__main__":
    unittest.main()
