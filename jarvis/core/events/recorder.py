"""Optional JSONL event recorder."""

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
import uuid

from jarvis.core.events.event import BaseEvent


class EventRecorder:
    """Append events to a JSONL file for replay/debugging."""

    def __init__(self, path="output/events/events.jsonl", enabled=True):
        """Create recorder."""
        self.path = Path(path)
        self.enabled = bool(enabled)

    def record(self, event):
        """Append one event when enabled."""
        if not self.enabled:
            return None

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(event.to_json())
            handle.write("\n")
        return self.path

    def flush(self):
        """Flush recorder state. Kept for future async/file buffering."""
        return True

    def close(self):
        """Close recorder resources."""
        return self.flush()

    def read_events(self):
        """Read recorded events for replay."""
        if not self.path.exists():
            return []

        events = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if text:
                    events.append(BaseEvent.from_json(text))
        return events


class DeadLetterRecorder(EventRecorder):
    """Record failed handler deliveries for later inspection."""

    def __init__(self, path="output/events/dead_letters.jsonl", enabled=True):
        """Create dead-letter recorder."""
        super().__init__(path=path, enabled=enabled)
        self.dead_letters = {}

    def record_failure(self, event, handler, error):
        """Record one failed handler delivery."""
        if not self.enabled:
            return ""

        dead_letter = DeadLetter(
            dead_letter_id=new_dead_letter_id(),
            event=event.to_dict(),
            handler=str(handler),
            attempts=1,
            error_type=error.__class__.__name__ if error is not None else "",
            error_message=str(error or ""),
            failed_at=datetime.now().isoformat(timespec="seconds"),
        )
        self.dead_letters[dead_letter.dead_letter_id] = dead_letter
        self.write_dead_letter(dead_letter)
        return dead_letter.dead_letter_id

    def list_dead_letters(self, status=None):
        """Return dead letters, optionally filtered by status."""
        values = list(self.dead_letters.values())

        if status:
            values = [item for item in values if item.status == status]

        return values

    def get_dead_letter(self, dead_letter_id):
        """Return one dead letter by ID."""
        return self.dead_letters.get(str(dead_letter_id or ""))

    def retry_dead_letter(self, dead_letter_id, event_bus, bypass_idempotency=False):
        """Republish a dead letter event."""
        dead_letter = self.get_dead_letter(dead_letter_id)

        if dead_letter is None:
            return None

        event = BaseEvent.from_dict(dead_letter.event)
        result = event_bus.publish(event, bypass_idempotency=bypass_idempotency)
        status = "RESOLVED" if result.success else "RETRIED"
        updated = replace(
            dead_letter,
            attempts=dead_letter.attempts + 1,
            status=status,
            resolved_at=datetime.now().isoformat(timespec="seconds") if result.success else "",
            resolution_note="retry_success" if result.success else "retry_failed",
        )
        self.dead_letters[dead_letter.dead_letter_id] = updated
        self.write_dead_letter(updated)
        return result

    def mark_resolved(self, dead_letter_id, note=""):
        """Mark one dead letter as resolved."""
        return self.update_status(dead_letter_id, "RESOLVED", note)

    def discard_dead_letter(self, dead_letter_id, note=""):
        """Mark one dead letter as discarded."""
        return self.update_status(dead_letter_id, "DISCARDED", note)

    def update_status(self, dead_letter_id, status, note):
        """Update status for one dead letter."""
        dead_letter = self.get_dead_letter(dead_letter_id)

        if dead_letter is None:
            return None

        updated = replace(
            dead_letter,
            status=status,
            resolved_at=datetime.now().isoformat(timespec="seconds"),
            resolution_note=str(note or status.lower()),
        )
        self.dead_letters[dead_letter.dead_letter_id] = updated
        self.write_dead_letter(updated)
        return updated

    def write_dead_letter(self, dead_letter):
        """Append one dead-letter state record."""
        if not self.enabled:
            return None

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(dead_letter.to_json())
            handle.write("\n")
        return self.path


@dataclass(frozen=True)
class DeadLetter:
    """One failed handler delivery."""

    dead_letter_id: str
    event: dict
    handler: str
    record_type: str = "DeadLetter"
    attempts: int = 1
    error_type: str = ""
    error_message: str = ""
    failed_at: str = ""
    status: str = "PENDING"
    resolved_at: str = ""
    resolution_note: str = ""

    def to_dict(self):
        """Return a JSON-safe dead letter."""
        return asdict(self)

    def to_json(self):
        """Return a JSON line."""
        import json

        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class ReplayOptions:
    """Options controlling safe event replay."""

    dry_run: bool = True
    event_types: tuple = field(default_factory=tuple)
    handler_names: tuple = field(default_factory=tuple)
    from_time: str = ""
    to_time: str = ""
    preserve_event_id: bool = True
    bypass_idempotency: bool = False


@dataclass(frozen=True)
class ReplayResult:
    """Replay preview or execution summary."""

    dry_run: bool
    events: int = 0
    handlers: int = 0
    would_execute: int = 0
    would_skip_duplicate: int = 0
    publish_results: tuple = field(default_factory=tuple)


def replay_events(path, event_bus, event_types=None, dry_run=True, bypass_idempotency=False, options=None):
    """Replay recorded JSONL events into an EventBus."""
    options = options or ReplayOptions(
        dry_run=dry_run,
        event_types=tuple(event_types or ()),
        bypass_idempotency=bypass_idempotency,
    )
    recorder = EventRecorder(path=path)
    allowed = set(options.event_types or ())
    results = []
    events = []

    for event in recorder.read_events():
        if allowed and event.event_type not in allowed:
            continue
        if options.from_time and event.occurred_at < options.from_time:
            continue
        if options.to_time and event.occurred_at > options.to_time:
            continue
        events.append(event)

    if options.dry_run:
        would_execute = 0
        would_skip_duplicate = 0

        for event in events:
            handler_count = len(event_bus.matching_handlers(event, handler_names=options.handler_names))
            if event.idempotency_key and not options.bypass_idempotency and event_bus.idempotency_store.get(event.idempotency_key):
                would_skip_duplicate += handler_count
            else:
                would_execute += handler_count

        return ReplayResult(
            dry_run=True,
            events=len(events),
            handlers=sum(len(event_bus.matching_handlers(event, handler_names=options.handler_names)) for event in events),
            would_execute=would_execute,
            would_skip_duplicate=would_skip_duplicate,
        )

    for event in events:
        replay_event = event if options.preserve_event_id else replace(event, event_id="")
        results.append(
            event_bus.publish(
                replay_event,
                bypass_idempotency=options.bypass_idempotency,
                handler_names=options.handler_names,
            )
        )
        event_bus.metrics.replayed_total += 1

    return ReplayResult(
        dry_run=False,
        events=len(events),
        handlers=sum(len(result.handler_results) for result in results),
        publish_results=tuple(results),
    )

def new_dead_letter_id():
    """Return a compact dead-letter ID."""
    return f"DL-{uuid.uuid4().hex[:10].upper()}"
