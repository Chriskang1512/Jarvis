import os
import hashlib
import re
import uuid
from pathlib import Path
from dataclasses import replace
from time import perf_counter

from jarvis.abilities.metadata import AbilityMetadata, AbilityType
from jarvis.abilities.native.mail.parser import MailIntentParser, normalize_query
from jarvis.abilities.native.mail.result import MailResult, MailSendResult, OutgoingMail
from jarvis.abilities.native.contacts.query import ContactQuery
from jarvis.abilities.result import AbilityHealth, AbilityResult
from jarvis.debug_trace import trace_event
from jarvis.permissions import PermissionLevel


class MailAbility:
    """Native Mail Ability backed by a provider boundary."""

    def __init__(self, metadata=None, parser=None, provider=None, config=None, contacts_provider=None):
        """Create Mail Ability."""
        self.metadata = metadata or load_mail_metadata()
        self.parser = parser or MailIntentParser()
        self.provider = provider if provider is not None else create_mail_provider(config=config)
        self.contacts_provider = contacts_provider
        self.last_messages = ()
        self.last_selected_message = None
        self._sending_fingerprints = set()
        self._sent_fingerprints = set()

    @property
    def id(self):
        return self.metadata.id

    @property
    def name(self):
        return self.metadata.name

    @property
    def type(self):
        return self.metadata.type

    @property
    def description(self):
        return self.metadata.description

    @property
    def permission(self):
        return self.metadata.permission

    @property
    def provider_name(self):
        if self.provider is not None:
            return getattr(self.provider, "provider_name", "mail_provider")
        return "mock_mail"

    def execute(self, input_data):
        """Execute a read-only mail action."""
        started = perf_counter()
        query = normalize_query(input_data, self.parser)
        trace_event("mail.query", action=query.action, query=query.query, ordinal=query.ordinal)

        try:
            if query.action in {"send", "reply"}:
                query, preparation_error = self.prepare_outgoing_query(query)
                if preparation_error is not None:
                    return self.ability_result(preparation_error, query)

                if not is_confirmed(input_data):
                    trace_event(
                        "mail.permission",
                        action=query.action,
                        permission="confirm_required",
                        pending_action_id=query.pending_action_id,
                    )
                    preview = create_send_confirmation_result(query, self.provider_name)
                    return AbilityResult(
                        success=True,
                        data=preview,
                        metadata={"ability_id": self.id, "query": query, "permission": "confirm_required"},
                    )

            result = self.execute_query(query)
            result = attach_runtime_fields(result, self.provider_name, elapsed_ms(started))
            trace_event(
                "mail.result",
                action=result.action,
                success=result.success,
                provider=result.provider,
                message_count=getattr(result, "message_count", 0),
                error_code=result.error_code,
                execution_time_ms=result.execution_time_ms,
            )
            return self.ability_result(result, query)
        except Exception as error:
            return AbilityResult(success=False, error=str(error), metadata={"ability_id": self.id})

    def execute_query(self, query):
        """Execute one MailQuery."""
        if query.action == "get":
            message = self.message_from_query(query)
            if message is None:
                return MailResult(success=False, action="get", error_code="MAIL_NOT_FOUND")
            message, warning = self.mark_message_read(message)
            self.last_selected_message = message
            self.replace_cached_message(message)
            return MailResult(
                success=True,
                action="get",
                message=message,
                messages=(message,),
                message_count=1,
                warning=warning,
            )

        if self.provider is None:
            return MailResult(success=False, action=query.action, error_code="AUTH_REQUIRED")

        if query.action in {"send", "reply"}:
            return self.execute_send(query)
        if query.action == "search":
            result = self.provider.search_messages(query)
        else:
            result = self.provider.list_messages(query)

        if result.success:
            self.last_messages = tuple(result.messages or ())

        return result

    def prepare_outgoing_query(self, query):
        """Resolve a complete immutable draft before confirmation."""
        pending_action_id = query.pending_action_id or uuid.uuid4().hex
        query = replace(query, pending_action_id=pending_action_id)

        if query.action == "reply":
            target = self.reply_target(query)
            if target is None:
                return query, mail_error(query.action, "REPLY_TARGET_NOT_FOUND")
            subject = query.subject or reply_subject(getattr(target, "subject", ""))
            query = replace(
                query,
                message_id=getattr(target, "id", ""),
                reply_to_message_id=getattr(target, "id", ""),
                reply_to_header=getattr(target, "rfc_message_id", ""),
                thread_id=getattr(target, "thread_id", ""),
                recipient=getattr(target, "sender_email", ""),
                recipient_name=getattr(target, "sender_name", ""),
                to=(getattr(target, "sender_email", ""),),
                subject=subject,
            )
        elif not query.to:
            query, resolution_error = self.resolve_recipient(query)
            if resolution_error is not None:
                return query, resolution_error

        validation_error = validate_outgoing_query(query)
        if validation_error:
            return query, mail_error(query.action, validation_error)
        return query, None

    def resolve_recipient(self, query):
        """Resolve direct email first, then an exact Google Contact."""
        recipient = str(query.recipient or "").strip()
        if is_valid_email(recipient):
            return replace(query, to=(recipient,)), None

        if recipient == "":
            return query, mail_error(query.action, "RECIPIENT_NOT_FOUND")
        if self.contacts_provider is None:
            return query, mail_error(query.action, "RECIPIENT_NOT_FOUND")

        result = self.contacts_provider.get_contact(
            ContactQuery(action="get", display_name=recipient, attribute="email")
        )
        code = str(getattr(result, "error_code", "") or "")
        if code in {"contact_ambiguous", "AMBIGUOUS_RECIPIENT"}:
            return query, mail_error(query.action, "AMBIGUOUS_RECIPIENT")
        contact = getattr(result, "contact", None)
        if not getattr(result, "success", False) or contact is None:
            return query, mail_error(query.action, "RECIPIENT_NOT_FOUND")
        emails = tuple(str(value).strip() for value in getattr(contact, "emails", ()) or () if str(value).strip())
        if not emails:
            return query, mail_error(query.action, "RECIPIENT_EMAIL_MISSING", recipient_name=recipient)
        if not is_valid_email(emails[0]):
            return query, mail_error(query.action, "INVALID_EMAIL_ADDRESS")
        return replace(
            query,
            recipient_name=getattr(contact, "display_name", "") or recipient,
            recipient=emails[0],
            to=(emails[0],),
        ), None

    def reply_target(self, query):
        """Resolve explicit, ordinal, or last-read reply context."""
        if query.message_id and self.provider is not None:
            result = self.provider.get_message(query.message_id)
            if getattr(result, "success", False):
                return result.message
        if query.ordinal > 0:
            return self.message_from_query(query)
        return self.last_selected_message

    def execute_send(self, query):
        """Send once after confirmation and block duplicate execution."""
        fingerprint = outgoing_fingerprint(query)
        if fingerprint in self._sending_fingerprints or fingerprint in self._sent_fingerprints:
            return mail_error(query.action, "DUPLICATE_SEND_BLOCKED", duplicate_blocked=True)

        self._sending_fingerprints.add(fingerprint)
        outgoing = outgoing_from_query(query)
        try:
            if query.action == "reply":
                result = self.provider.reply_message(outgoing)
            else:
                result = self.provider.send_message(outgoing)

            if getattr(result, "success", False) or getattr(result, "message_id", ""):
                self._sent_fingerprints.add(fingerprint)
            return result
        finally:
            self._sending_fingerprints.discard(fingerprint)

    def ability_result(self, result, query):
        """Wrap a Mail result with stable metadata."""
        return AbilityResult(
            success=result.success,
            data=result,
            error=result.to_natural_language() if not result.success else "",
            metadata={"ability_id": self.id, "query": query},
        )

    def message_from_query(self, query):
        """Return one message from id or recent ordinal."""
        if query.message_id and self.provider is not None:
            result = self.provider.get_message(query.message_id)
            return result.message if result.success else None

        if query.ordinal > 0:
            index = query.ordinal - 1
            if 0 <= index < len(self.last_messages):
                message = self.last_messages[index]
                if self.provider is not None and message.id:
                    result = self.provider.get_message(message.id)
                    return result.message if result.success else message
                return message

        return None

    def mark_message_read(self, message):
        """Mark a successfully opened unread message as read when supported."""
        if not getattr(message, "unread", False):
            return message, ""
        if self.provider is None or not hasattr(self.provider, "mark_read"):
            return message, ""

        result = self.provider.mark_read(getattr(message, "id", ""))
        if not getattr(result, "success", False):
            return message, "Gmail 읽음 상태를 변경하지 못했습니다."
        labels = tuple(label for label in getattr(message, "labels", ()) or () if label != "UNREAD")
        return replace(message, unread=False, labels=labels), ""

    def replace_cached_message(self, message):
        """Keep the session's recent-mail cache consistent after a state change."""
        message_id = getattr(message, "id", "")
        self.last_messages = tuple(
            message if getattr(item, "id", "") == message_id else item
            for item in self.last_messages
        )

    def health(self):
        return AbilityHealth(status="ok", provider=self.provider_name, message="Mail ability is ready.")


def load_mail_metadata():
    """Load Mail manifest."""
    import json

    manifest_path = Path(__file__).with_name("manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return AbilityMetadata(
        id=manifest["id"],
        name=manifest["name"],
        type=AbilityType(manifest["type"]),
        permission=PermissionLevel(manifest["permission"]),
        version=manifest["version"],
        author=manifest.get("author", "Jarvis"),
        description=manifest["description"],
        capabilities=list(manifest.get("capabilities", [])),
        input_schema=dict(manifest.get("input_schema", {})),
        output_schema=manifest.get("output_schema", "MailResult"),
        aliases=list(manifest.get("aliases", [])),
        supported_intents=list(manifest.get("supported_intents", [])),
        examples=list(manifest.get("examples", [])),
        input_prefixes=list(manifest.get("input_prefixes", [])),
        route_confidence=float(manifest.get("route_confidence", 0.75)),
    )


def create_mail_provider(config=None):
    """Create optional Google Mail provider from config or environment."""
    provider_name = str(os.environ.get("JARVIS_MAIL_PROVIDER", "") or getattr(config, "provider", "") or "").lower()

    if provider_name != "google":
        return None

    from jarvis.providers.google.config import GOOGLE_GMAIL_MODIFY_SCOPE, GoogleProviderConfig
    from jarvis.providers.google.gmail import GoogleMailProvider

    google_config = GoogleProviderConfig(
        credentials_path=os.environ.get(
            "JARVIS_GOOGLE_TOKEN_PATH",
            getattr(config, "google_credentials_path", "data/credentials/google_token.json"),
        ),
        client_secret_path=os.environ.get(
            "JARVIS_GOOGLE_CLIENT_SECRET_PATH",
            getattr(config, "google_client_secret_path", "client_secret.json"),
        ),
        scopes=(GOOGLE_GMAIL_MODIFY_SCOPE,),
    )
    return GoogleMailProvider(config=google_config)


def create_ability():
    """Create Mail Ability."""
    return MailAbility()


def attach_runtime_fields(result, provider, execution_time_ms):
    """Return result with common runtime fields."""
    from dataclasses import replace

    return replace(result, provider=result.provider or provider, execution_time_ms=execution_time_ms)


def elapsed_ms(started):
    return int((perf_counter() - started) * 1000)


def is_confirmed(input_data):
    """Return whether Permission confirmation was supplied."""
    if isinstance(input_data, dict):
        return bool(input_data.get("_confirmed", input_data.get("confirmed", False)))
    return bool(getattr(input_data, "confirmed", False))


def is_valid_email(value):
    """Validate one practical RFC 5322 mailbox address."""
    return re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\.[A-Za-z]{2,63}", str(value or "").strip()) is not None


def validate_outgoing_query(query):
    """Return the first stable validation error code."""
    if not query.to:
        return "RECIPIENT_NOT_FOUND"
    if any(not is_valid_email(address) for address in (*query.to, *query.cc, *query.bcc)):
        return "INVALID_EMAIL_ADDRESS"
    if str(query.subject or "").strip() == "":
        return "MAIL_SUBJECT_REQUIRED"
    if str(query.body or "").strip() == "":
        return "MAIL_BODY_REQUIRED"
    if query.action == "reply" and str(query.reply_to_message_id or "").strip() == "":
        return "REPLY_TARGET_NOT_FOUND"
    return ""


def outgoing_from_query(query):
    """Build the provider-independent draft."""
    return OutgoingMail(
        to=tuple(query.to),
        cc=tuple(query.cc),
        bcc=tuple(query.bcc),
        subject=query.subject,
        body=query.body,
        reply_to_message_id=query.reply_to_message_id,
        reply_to_header=query.reply_to_header,
        thread_id=query.thread_id,
        pending_action_id=query.pending_action_id,
        recipient_name=query.recipient_name,
    )


def create_send_confirmation_result(query, provider):
    """Return a preview without calling Gmail."""
    return MailResult(
        success=True,
        action=query.action,
        provider=provider,
        requires_confirmation=True,
        outgoing=outgoing_from_query(query),
    )


def mail_error(action, code, recipient_name="", duplicate_blocked=False):
    """Return a stable send error result."""
    return MailSendResult(
        success=False,
        action=action,
        error_code=code,
        recipient_name=recipient_name,
        duplicate_blocked=duplicate_blocked,
    )


def outgoing_fingerprint(query):
    """Return a stable per-pending-action send fingerprint."""
    value = "\x1f".join(
        [
            query.pending_action_id,
            ",".join(sorted(address.lower() for address in query.to)),
            query.subject.strip(),
            hashlib.sha256(query.body.encode("utf-8")).hexdigest(),
        ]
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def reply_subject(subject):
    """Return one predictable reply subject."""
    value = str(subject or "").strip()
    return value if value.lower().startswith("re:") else f"Re: {value or '답장'}"
