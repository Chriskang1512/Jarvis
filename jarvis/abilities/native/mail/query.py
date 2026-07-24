from dataclasses import dataclass


@dataclass(frozen=True)
class MailQuery:
    """Structured input for Mail Ability."""

    action: str = "list"
    query: str = ""
    sender: str = ""
    label: str = ""
    unread: bool = False
    today: bool = False
    limit: int = 5
    message_id: str = ""
    thread_id: str = ""
    ordinal: int = 0
    include_body: bool = False
    recipient: str = ""
    recipient_name: str = ""
    to: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()
    subject: str = ""
    body: str = ""
    reply_to_message_id: str = ""
    reply_to_header: str = ""
    pending_action_id: str = ""
    confirmed: bool = False
    raw_text: str = ""

    def to_input_data(self):
        """Return a dispatcher-safe dictionary."""
        return {
            "action": self.action,
            "query": self.query,
            "sender": self.sender,
            "label": self.label,
            "unread": self.unread,
            "today": self.today,
            "limit": self.limit,
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "ordinal": self.ordinal,
            "include_body": self.include_body,
            "recipient": self.recipient,
            "recipient_name": self.recipient_name,
            "to": list(self.to),
            "cc": list(self.cc),
            "bcc": list(self.bcc),
            "subject": self.subject,
            "body": self.body,
            "reply_to_message_id": self.reply_to_message_id,
            "reply_to_header": self.reply_to_header,
            "pending_action_id": self.pending_action_id,
            "confirmed": self.confirmed,
            "raw_text": self.raw_text,
        }
