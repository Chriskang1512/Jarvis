from dataclasses import dataclass, field

from jarvis.abilities.result import BaseAbilityResult


@dataclass(frozen=True)
class MailMessage:
    """One normalized mail message."""

    id: str = ""
    thread_id: str = ""
    sender_name: str = ""
    sender_email: str = ""
    subject: str = ""
    snippet: str = ""
    received_at: str = ""
    unread: bool = False
    labels: tuple[str, ...] = field(default_factory=tuple)
    has_attachment: bool = False
    attachment_count: int = 0
    body_summary: str = ""
    to: tuple[str, ...] = field(default_factory=tuple)
    rfc_message_id: str = ""


@dataclass(frozen=True)
class OutgoingMail:
    """Provider-independent mail draft."""

    to: tuple[str, ...] = field(default_factory=tuple)
    cc: tuple[str, ...] = field(default_factory=tuple)
    bcc: tuple[str, ...] = field(default_factory=tuple)
    subject: str = ""
    body: str = ""
    reply_to_message_id: str = ""
    reply_to_header: str = ""
    thread_id: str = ""
    pending_action_id: str = ""
    recipient_name: str = ""


@dataclass(frozen=True)
class MailSendResult(BaseAbilityResult):
    """Normalized Gmail send result."""

    action: str = "send"
    message_id: str = ""
    thread_id: str = ""
    recipient: str = ""
    recipient_name: str = ""
    subject: str = ""
    verified: bool = False
    duplicate_blocked: bool = False
    user_message: str = ""

    def to_natural_language(self):
        """Return a safe send response."""
        from jarvis.abilities.native.mail.formatter import format_mail_send_result

        return format_mail_send_result(self)


@dataclass(frozen=True)
class MailResult(BaseAbilityResult):
    """Structured Mail Ability result."""

    action: str = ""
    message: MailMessage | None = None
    messages: tuple[MailMessage, ...] = field(default_factory=tuple)
    message_count: int = 0
    query: str = ""
    requires_confirmation: bool = False
    user_message: str = ""
    outgoing: OutgoingMail | None = None
    send_result: MailSendResult | None = None

    def to_natural_language(self):
        """Return formatted response."""
        from jarvis.abilities.native.mail.formatter import format_mail_result

        return format_mail_result(self)
