from dataclasses import dataclass, field

from jarvis.native.reminder.reminder import ReminderEntry


@dataclass(frozen=True)
class ReminderResult:
    """Reminder Ability result payload."""

    success: bool
    action: str
    reminders: list[ReminderEntry] = field(default_factory=list)
    count: int = 0
    provider: str = "mock"
    message: str = ""

    def __post_init__(self):
        """Fill count from reminders."""
        if self.count == 0 and len(self.reminders) > 0:
            object.__setattr__(self, "count", len(self.reminders))

    def to_natural_language(self):
        """Return a concise Korean response."""
        if self.message:
            return self.message

        if self.action == "create" and self.success:
            return "\uc54c\ub9bc\uc744 \ub4f1\ub85d\ud588\uc2b5\ub2c8\ub2e4."

        if self.action == "cancel" and self.success:
            return "\uc54c\ub9bc\uc744 \ucde8\uc18c\ud588\uc2b5\ub2c8\ub2e4."

        if self.action == "update" and self.success:
            return "\uc54c\ub9bc\uc744 \uc218\uc815\ud588\uc2b5\ub2c8\ub2e4."

        if self.action == "list":
            if len(self.reminders) == 0:
                return "\ub4f1\ub85d\ub41c \uc54c\ub9bc\uc774 \uc5c6\uc2b5\ub2c8\ub2e4."

            return f"\uc54c\ub9bc\uc774 {len(self.reminders)}\uac74 \uc788\uc2b5\ub2c8\ub2e4."

        return str(self)
