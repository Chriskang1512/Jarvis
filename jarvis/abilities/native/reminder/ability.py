import json
import re
from pathlib import Path

from jarvis.abilities.metadata import AbilityMetadata, AbilityType
from jarvis.abilities.native.reminder.parser import ReminderIntentParser
from jarvis.abilities.result import AbilityHealth, AbilityResult
from jarvis.debug_trace import trace_event
from jarvis.native.reminder.registry import get_default_reminder_engine
from jarvis.native.reminder.result import ReminderResult
from jarvis.permissions import PermissionLevel


class ReminderAbility:
    """Native Reminder Ability backed by ReminderEngine."""

    def __init__(self, engine=None, metadata=None, parser=None):
        """Create Reminder Ability."""
        self.engine = engine or get_default_reminder_engine()
        self.metadata = metadata or load_reminder_metadata()
        self.parser = parser or ReminderIntentParser()

    @property
    def id(self):
        """Return ability ID."""
        return self.metadata.id

    def execute(self, input_data):
        """Execute reminder action."""
        try:
            query = normalize_query(input_data, self.parser)
            trace_event(
                "reminder.query",
                action=query.action,
                title=query.title,
                datetime=query.datetime,
                remind_before=query.remind_before,
            )

            if query.action == "list":
                reminders = self.engine.list(state="pending")
                return AbilityResult(
                    success=True,
                    data=ReminderResult(True, "list", reminders=reminders, provider=self.engine.provider),
                    metadata={"ability_id": self.id},
                )

            if query.action == "cancel":
                cancelled = self.cancel_reminders(query)

                return AbilityResult(
                    success=True,
                    data=ReminderResult(True, "cancel", reminders=[item for item in cancelled if item], provider=self.engine.provider),
                    metadata={"ability_id": self.id},
                )

            if query.action == "delete":
                cancelled = self.cancel_reminders(query)

                return AbilityResult(
                    success=True,
                    data=ReminderResult(True, "cancel", reminders=[item for item in cancelled if item], provider=self.engine.provider),
                    metadata={"ability_id": self.id},
                )

            if query.action == "update":
                reminder = self.update_reminder(query)

                return AbilityResult(
                    success=reminder is not None,
                    data=ReminderResult(reminder is not None, "update", reminders=[reminder] if reminder else [], provider=self.engine.provider),
                    error="" if reminder is not None else "Reminder not found.",
                    metadata={"ability_id": self.id, "reminder_id": getattr(reminder, "id", "") if reminder else ""},
                )

            create_error = validate_create_query(query)

            if create_error:
                result = ReminderResult(False, "create", provider=self.engine.provider, message=create_error)
                return AbilityResult(
                    success=False,
                    data=result,
                    error=create_error,
                    metadata={"ability_id": self.id, "error_code": "time_required"},
                )

            reminder = self.engine.create(
                query.title,
                query.datetime,
                remind_before=query.remind_before,
                recurrence=getattr(query, "recurrence", ""),
                snooze_until=getattr(query, "snooze_until", ""),
                priority=getattr(query, "priority", "normal"),
            )
            return AbilityResult(
                success=True,
                data=ReminderResult(True, "create", reminders=[reminder], provider=self.engine.provider),
                metadata={"ability_id": self.id, "reminder_id": reminder.id},
            )
        except Exception as error:
            return AbilityResult(success=False, error=str(error), metadata={"ability_id": self.id})

    def cancel_reminders(self, query):
        """Cancel reminders by id, calendar id, or all pending reminders."""
        reminder_id = str(getattr(query, "reminder_id", "") or "")
        calendar_id = str(getattr(query, "calendar_id", "") or "")

        if reminder_id:
            cancelled = self.engine.queue.cancel(reminder_id)
            return [cancelled] if cancelled else []

        if calendar_id:
            return self.engine.delete_by_source("calendar", calendar_id)

        cancelled = []

        for reminder in self.engine.list(state="pending"):
            cancelled.append(self.engine.queue.cancel(reminder.id))

        return [item for item in cancelled if item]

    def update_reminder(self, query):
        """Patch one reminder by id or calendar id."""
        reminder_id = str(getattr(query, "reminder_id", "") or "")
        calendar_id = str(getattr(query, "calendar_id", "") or "")

        if reminder_id == "" and calendar_id:
            for reminder in self.engine.list(state="pending"):
                if reminder.calendar_id == calendar_id:
                    reminder_id = reminder.id
                    break

        if reminder_id == "":
            return None

        changes = {
            "title": query.title,
            "datetime": query.datetime,
            "remind_before": query.remind_before,
            "recurrence": getattr(query, "recurrence", ""),
            "snooze_until": getattr(query, "snooze_until", ""),
            "priority": getattr(query, "priority", ""),
        }
        return self.engine.update(reminder_id, **changes)

    def health(self):
        """Return health."""
        return AbilityHealth(status="ok", provider=self.engine.provider)


def normalize_query(input_data, parser=None):
    """Return ReminderQuery."""
    from jarvis.abilities.native.reminder.parser import ReminderQuery

    if hasattr(input_data, "action") and hasattr(input_data, "datetime"):
        return input_data

    if isinstance(input_data, dict) and "action" in input_data:
        action = str(input_data.get("action", "create"))
        default_remind_before = 30 if action == "create" else None
        remind_before = input_data.get("remind_before", default_remind_before)
        return ReminderQuery(
            action=action,
            title=str(input_data.get("title", "")),
            datetime=str(input_data.get("datetime", "")),
            remind_before=None if remind_before is None else int(remind_before),
            raw_text=str(input_data.get("raw_text", "")),
            recurrence=str(input_data.get("recurrence", "")),
            snooze_until=str(input_data.get("snooze_until", "")),
            priority=str(input_data.get("priority", "normal")),
            reminder_id=str(input_data.get("reminder_id", "")),
            calendar_id=str(input_data.get("calendar_id", "")),
        )

    raw_text = ""

    if isinstance(input_data, dict):
        raw_text = input_data.get("text") or input_data.get("raw_text") or ""
    else:
        raw_text = str(input_data or "")

    return (parser or ReminderIntentParser()).parse(raw_text)


def validate_create_query(query):
    """Return a user-facing error when a reminder create query is unsafe."""
    if getattr(query, "action", "") != "create":
        return ""

    raw_text = str(getattr(query, "raw_text", "") or "")

    if raw_text and not has_explicit_reminder_time(raw_text):
        return "알림 시간을 다시 말씀해 주세요."

    if str(getattr(query, "datetime", "") or "") == "":
        return "알림 시간을 다시 말씀해 주세요."

    return ""


def has_explicit_reminder_time(text):
    """Return whether text contains an explicit reminder time or relative delay."""
    compact = str(text or "").replace(" ", "")

    if re.search(r"\d+(분|시간)(뒤|후)", compact):
        return True

    if re.search(r"\d+(분|시간)전", compact):
        return True

    if re.search(r"(오전|오후)?\d{1,2}시", compact):
        return True

    if re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", compact):
        return True

    return False


def load_reminder_metadata():
    """Load Reminder manifest."""
    manifest = json.loads(Path(__file__).with_name("manifest.json").read_text(encoding="utf-8"))

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
        output_schema=manifest.get("output_schema", "ReminderResult"),
        aliases=[
            "reminder",
            "scheduler",
            "notification",
            "알림",
            "알람",
            "리마인더",
            "분 뒤",
            "분 후",
            "시간 뒤",
            "시간 후",
        ],
        supported_intents=[
            "알림",
            "알람",
            "리마인더",
            "1분 뒤 알람 등록해",
            "30분 뒤 알려줘",
            "30분 전에 알려줘",
            "알림 끄기",
        ],
        examples=["내일 오후 3시 아야 만나기 30분 전 알림 등록해"],
        input_prefixes=["reminder", "알림", "알람", "리마인더"],
        route_confidence=0.75,
    )


def create_ability(engine=None):
    """Factory used by registries."""
    return ReminderAbility(engine=engine)
