"""Google Gmail read/send provider."""

import base64
import hashlib
from email.message import EmailMessage
from time import perf_counter

from jarvis.abilities.native.mail.result import MailResult, MailSendResult
from jarvis.debug_trace import trace_event
from jarvis.privacy import redact_sensitive_text
from jarvis.providers.google.config import GOOGLE_GMAIL_READONLY_SCOPE, GOOGLE_GMAIL_SEND_SCOPE, GoogleProviderConfig
from jarvis.providers.google.context import GoogleProviderContext
from jarvis.providers.google.errors import (
    AUTH_EXPIRED,
    AUTH_REFRESH_FAILED,
    AUTH_REQUIRED,
    FEATURE_NOT_ENABLED,
    PERMISSION_DENIED,
    PROVIDER_TIMEOUT,
    PROVIDER_UNAVAILABLE,
    RATE_LIMITED,
    SCOPE_INSUFFICIENT,
    GoogleProviderError,
)
from jarvis.providers.google.gmail.mapper import GoogleMailMapper


class GoogleMailProvider:
    """Read and safely send Gmail messages through Gmail API."""

    provider_name = "google_gmail"

    def __init__(self, client=None, mapper=None, config=None, context=None):
        """Create provider with optional fake client for tests."""
        config = config or GoogleProviderConfig(scopes=(GOOGLE_GMAIL_READONLY_SCOPE, GOOGLE_GMAIL_SEND_SCOPE))
        self.context = context or GoogleProviderContext.create(config=config)
        self.config = self.context.config
        self.client = client
        self.client_factory = self.context.client_factory
        self.request_executor = self.context.request_executor
        self.error_mapper = self.context.error_mapper
        self.mapper = mapper or GoogleMailMapper()

    def list_messages(self, query):
        """List recent Gmail messages."""
        return self.search_messages(query)

    def search_messages(self, query):
        """Search Gmail messages and hydrate compact metadata."""
        started = perf_counter()
        gmail_query = str(getattr(query, "query", "") or "").strip()
        inbox_query = " ".join(part for part in ("-in:sent", gmail_query) if part)
        limit = int(getattr(query, "limit", 5) or 5)
        limit = max(1, min(limit, 10))
        trace_event(
            "google_gmail.request",
            action="search",
            provider=self.provider_name,
            mailbox="inbox",
            query=redact_sensitive_text(gmail_query),
            limit=limit,
        )

        try:
            service = self.gmail_client()
            response = self.execute_google_request(
                lambda: service.users().messages().list(
                    userId="me",
                    q=inbox_query,
                    labelIds=["INBOX"],
                    maxResults=limit,
                )
            )
            refs = self.mapper.list_to_messages(response)
            messages = tuple(self.hydrate_message(ref.id, service=service) for ref in refs if ref.id)
            messages = tuple(message for message in messages if message is not None)
            trace_event("google_gmail.response", messages=len(messages), provider=self.provider_name)
            return MailResult(
                success=True,
                action="search" if gmail_query else "list",
                messages=messages,
                message_count=len(messages),
                query=gmail_query,
                provider=self.provider_name,
                execution_time_ms=elapsed_ms(started),
            )
        except GoogleProviderError as error:
            return self.error_result("search", error, started, gmail_query)
        except Exception as error:
            return self.error_result("search", self.error_mapper.map_exception(error), started, gmail_query)

    def get_message(self, message_id):
        """Get one Gmail message by id."""
        started = perf_counter()
        trace_event("google_gmail.request", action="get", provider=self.provider_name, message_id=redact_sensitive_text(message_id))

        try:
            service = self.gmail_client()
            message = self.hydrate_message(message_id, service=service)
            trace_event("google_gmail.response", messages=1 if message is not None else 0, provider=self.provider_name)
            return MailResult(
                success=message is not None,
                action="get",
                message=message,
                messages=(message,) if message is not None else (),
                message_count=1 if message is not None else 0,
                provider=self.provider_name,
                error_code="" if message is not None else "MAIL_NOT_FOUND",
                execution_time_ms=elapsed_ms(started),
            )
        except GoogleProviderError as error:
            return self.error_result("get", error, started)
        except Exception as error:
            return self.error_result("get", self.error_mapper.map_exception(error), started)

    def send_message(self, outgoing):
        """Send a completed provider-independent draft and verify metadata."""
        return self._send_outgoing(outgoing, action="send")

    def reply_message(self, outgoing):
        """Reply within the selected Gmail thread and verify metadata."""
        return self._send_outgoing(outgoing, action="reply")

    def _send_outgoing(self, outgoing, action):
        """Build MIME, send once, and verify the sent metadata."""
        started = perf_counter()
        recipient = first_recipient(outgoing)
        trace_event(
            "google_gmail.send.request",
            action=action,
            provider=self.provider_name,
            to=redact_sensitive_text(recipient),
            subject_hash=short_hash(getattr(outgoing, "subject", "")),
            body_length=len(str(getattr(outgoing, "body", "") or "")),
            pending_action_id=short_hash(getattr(outgoing, "pending_action_id", "")),
        )

        try:
            service = self.gmail_client()
            raw_message = build_raw_message(outgoing)
            request_body = {"raw": raw_message}
            if getattr(outgoing, "thread_id", ""):
                request_body["threadId"] = outgoing.thread_id
            response = self.execute_google_request(
                lambda: service.users().messages().send(userId="me", body=request_body)
            )
            message_id = str(dict(response or {}).get("id") or "")
            thread_id = str(dict(response or {}).get("threadId") or "")
            if not message_id:
                return send_error_result(action, "SEND_FAILED", started)

            verified = self.verify_sent_message(
                service,
                message_id=message_id,
                expected_recipient=recipient,
                expected_subject=getattr(outgoing, "subject", ""),
            )
            trace_event(
                "google_gmail.send.response",
                action=action,
                provider=self.provider_name,
                message_id=short_hash(message_id),
                thread_id=short_hash(thread_id),
                verified=verified,
            )
            return MailSendResult(
                success=verified,
                action=action,
                message_id=message_id,
                thread_id=thread_id,
                recipient=recipient,
                recipient_name=getattr(outgoing, "recipient_name", ""),
                subject=getattr(outgoing, "subject", ""),
                verified=verified,
                provider=self.provider_name,
                error_code="" if verified else "SEND_FAILED",
                execution_time_ms=elapsed_ms(started),
            )
        except GoogleProviderError as error:
            return send_error_result(action, map_send_error_code(error.code), started)
        except Exception as error:
            mapped = self.error_mapper.map_exception(error)
            return send_error_result(action, map_send_error_code(mapped.code), started)

    def verify_sent_message(self, service, message_id, expected_recipient, expected_subject):
        """Verify recipient and subject using sent metadata only."""
        response = self.execute_google_request(
            lambda: service.users().messages().get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["To", "Subject"],
            )
        )
        message = self.mapper.to_message(response)
        recipients = {address.strip().lower() for address in getattr(message, "to", ()) or ()}
        return (
            str(getattr(message, "id", "") or "") == str(message_id)
            and str(expected_recipient or "").strip().lower() in recipients
            and str(getattr(message, "subject", "") or "").strip() == str(expected_subject or "").strip()
        )

    def hydrate_message(self, message_id, service=None):
        """Fetch one message as normalized MailMessage."""
        service = service or self.gmail_client()
        response = self.execute_google_request(
            lambda: service.users().messages().get(userId="me", id=message_id, format="full")
        )
        return self.mapper.to_message(response)

    def gmail_client(self):
        """Return Gmail client."""
        if self.client is not None:
            return self.client
        return self.client_factory.gmail_client()

    def execute_google_request(self, request_factory):
        """Execute one Google request or raise mapped provider error."""
        result = self.request_executor.execute(request_factory)
        if result.success:
            return result.response
        raise result.error

    def error_result(self, action, error, started, query=""):
        """Return structured provider error."""
        return MailResult(
            success=False,
            action=action,
            provider=self.provider_name,
            error_code=error.code,
            user_message=gmail_safe_message(error.code),
            query=query,
            execution_time_ms=elapsed_ms(started),
        )


def create_google_mail_provider(config=None):
    """Create Google Mail provider."""
    return GoogleMailProvider(config=config)


def gmail_safe_message(code):
    """Return Gmail-specific user-safe error text."""
    if code == AUTH_REQUIRED:
        return "Gmail 인증이 필요합니다."
    if code == AUTH_EXPIRED:
        return "Gmail 인증이 만료되었습니다."
    if code == AUTH_REFRESH_FAILED:
        return "Gmail 인증을 갱신하지 못했습니다."
    if code == SCOPE_INSUFFICIENT:
        return "Gmail 읽기 권한이 없습니다."
    if code == PERMISSION_DENIED:
        return "Gmail 접근 권한이 없습니다."
    if code == PROVIDER_TIMEOUT:
        return "Gmail 응답이 지연되고 있습니다."
    if code == RATE_LIMITED:
        return "Gmail 요청 한도를 초과했습니다."
    if code == PROVIDER_UNAVAILABLE:
        return "Gmail 서비스를 현재 사용할 수 없습니다."
    if code == FEATURE_NOT_ENABLED:
        return "Google Cloud에서 Gmail API를 활성화해야 합니다."
    return "Gmail 요청을 처리하지 못했습니다."


def elapsed_ms(started):
    """Return elapsed milliseconds."""
    return int((perf_counter() - started) * 1000)


def build_raw_message(outgoing):
    """Build one RFC 5322 message and return Gmail base64url data."""
    message = EmailMessage()
    message["To"] = ", ".join(tuple(getattr(outgoing, "to", ()) or ()))
    if getattr(outgoing, "cc", ()):
        message["Cc"] = ", ".join(tuple(outgoing.cc))
    if getattr(outgoing, "bcc", ()):
        message["Bcc"] = ", ".join(tuple(outgoing.bcc))
    message["Subject"] = str(getattr(outgoing, "subject", "") or "")
    pending_id = str(getattr(outgoing, "pending_action_id", "") or "")
    if pending_id:
        message["Message-ID"] = f"<jarvis-{pending_id}@local.invalid>"
        message["X-Jarvis-Pending-Action-ID"] = pending_id
    reply_to = str(getattr(outgoing, "reply_to_header", "") or "")
    if reply_to:
        message["In-Reply-To"] = reply_to
        message["References"] = reply_to
    message.set_content(str(getattr(outgoing, "body", "") or ""), subtype="plain", charset="utf-8")
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def first_recipient(outgoing):
    """Return the first To recipient."""
    recipients = tuple(getattr(outgoing, "to", ()) or ())
    return str(recipients[0] if recipients else "")


def short_hash(value):
    """Return a non-reversible short trace identifier."""
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]


def map_send_error_code(code):
    """Preserve auth errors and normalize send failures."""
    if code in {
        AUTH_REQUIRED,
        AUTH_EXPIRED,
        AUTH_REFRESH_FAILED,
        SCOPE_INSUFFICIENT,
        PERMISSION_DENIED,
        PROVIDER_TIMEOUT,
        PROVIDER_UNAVAILABLE,
        RATE_LIMITED,
        FEATURE_NOT_ENABLED,
    }:
        return code
    return "SEND_FAILED"


def send_error_result(action, code, started):
    """Return a safe Gmail send failure."""
    return MailSendResult(
        success=False,
        action=action,
        provider="google_gmail",
        error_code=code,
        execution_time_ms=elapsed_ms(started),
    )
