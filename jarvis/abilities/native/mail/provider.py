from typing import Protocol


class MailProvider(Protocol):
    """Provider contract for normalized mail reads, state changes, and sends."""

    def list_messages(self, query):
        """Return recent messages without changing read state."""

    def search_messages(self, query):
        """Return matching messages without changing read state."""

    def get_message(self, message_id):
        """Return one message including its readable body summary."""

    def mark_read(self, message_id):
        """Mark one successfully opened message as read."""

    def send_message(self, outgoing):
        """Send one confirmed new message."""

    def reply_message(self, outgoing):
        """Send one confirmed reply."""
