"""Privacy-safe, replayable execution journal for Agent Runtime tasks."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import html
import json
from pathlib import Path
import re
from uuid import uuid4


class JournalPhase(str, Enum):
    GOAL = "GOAL"
    PLAN = "PLAN"
    DISCOVERY = "DISCOVERY"
    VALIDATION = "VALIDATION"
    OPTIMIZATION = "OPTIMIZATION"
    PERMISSION = "PERMISSION"
    EXECUTION = "EXECUTION"
    VERIFICATION = "VERIFICATION"
    RECOVERY = "RECOVERY"
    CONVERSATION = "CONVERSATION"
    RESULT = "RESULT"


SAFE_METADATA_KEYS = {
    "action",
    "active_execution_ms",
    "availability",
    "capability",
    "checkpoint_fingerprint",
    "confidence",
    "contract_version",
    "cost",
    "decision",
    "duration_ms",
    "estimated_cost",
    "estimated_latency_ms",
    "implementation_id",
    "latency_ms",
    "lifecycle",
    "new_state",
    "operation",
    "permission",
    "plan_id",
    "plan_version",
    "previous_state",
    "provider",
    "reason",
    "recovery_strategy",
    "reliability_score",
    "resume_mode",
    "retry",
    "retry_count",
    "rule_id",
    "selected_implementation",
    "side_effect",
    "status",
    "step_count",
    "step_id",
    "transition_id",
    "transition_reason",
    "transition_source",
    "validation",
    "validator",
    "waiting_ms",
    "wall_clock_ms",
}
SENSITIVE_KEY_PARTS = {
    "address",
    "answer",
    "auth",
    "body",
    "content",
    "email",
    "header",
    "input",
    "message",
    "phone",
    "prompt",
    "recipient",
    "request",
    "subject",
    "text",
    "token",
    "transcript",
}
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


@dataclass(frozen=True)
class JournalEntry:
    id: str
    timestamp: str
    task_id: str
    sequence: int
    phase: JournalPhase
    event: str
    status: str
    metadata: dict = field(default_factory=dict)
    fingerprint: str = ""
    previous_fingerprint: str = ""

    def to_dict(self):
        data = asdict(self)
        data["phase"] = self.phase.value
        return data

    @classmethod
    def from_dict(cls, data):
        source = dict(data or {})
        source["phase"] = JournalPhase(source["phase"])
        return cls(**source)


@dataclass(frozen=True)
class JournalArtifact:
    artifact_id: str
    task_id: str
    artifact_type: str
    fingerprint: str
    created_at: str
    verified: bool = False
    size: int = 0
    media_type: str = ""
    sensitivity: str = "protected"


@dataclass(frozen=True)
class ReplayResult:
    task_id: str
    entries: tuple[JournalEntry, ...]
    valid: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExplainResult:
    task_id: str
    summary: str
    reasons: tuple[str, ...]
    status: str = ""


@dataclass(frozen=True)
class JournalSearchResult:
    query: str
    entries: tuple[JournalEntry, ...]

    @property
    def task_ids(self):
        return tuple(dict.fromkeys(entry.task_id for entry in self.entries))


class InMemoryJournalStore:
    """Append-only task journal and protected artifact-reference store."""

    def __init__(self):
        self._entries = {}
        self._artifacts = {}

    def append(self, entry):
        items = self._entries.setdefault(entry.task_id, [])
        if items and entry.sequence != items[-1].sequence + 1:
            raise ValueError("JOURNAL_SEQUENCE_INVALID")
        if not items and entry.sequence != 1:
            raise ValueError("JOURNAL_SEQUENCE_INVALID")
        items.append(entry)
        return entry

    def entries(self, task_id):
        return tuple(self._entries.get(str(task_id or ""), ()))

    def task_ids(self):
        return tuple(self._entries)

    def add_artifact(self, artifact):
        self._artifacts.setdefault(artifact.task_id, {})[artifact.artifact_id] = artifact
        return artifact

    def artifacts(self, task_id):
        return tuple(self._artifacts.get(str(task_id or ""), {}).values())


class ExecutionJournal:
    """Record, restore, replay, query, and explain Runtime decisions."""

    schema_version = 1

    def __init__(self, store=None, clock=None):
        self.store = store or InMemoryJournalStore()
        self.clock = clock or journal_now

    def record(self, task_id, phase, event, status="", metadata=None, timestamp=""):
        task_id = str(task_id or "")
        if not task_id:
            raise ValueError("JOURNAL_TASK_ID_REQUIRED")
        phase = phase if isinstance(phase, JournalPhase) else JournalPhase(str(phase))
        safe_metadata = sanitize_metadata(metadata)
        previous = self.store.entries(task_id)
        sequence = len(previous) + 1
        previous_fingerprint = previous[-1].fingerprint if previous else ""
        occurred_at = str(timestamp or self.clock())
        fingerprint = entry_fingerprint(
            task_id,
            sequence,
            phase.value,
            str(event or ""),
            str(status or ""),
            safe_metadata,
            previous_fingerprint,
        )
        return self.store.append(
            JournalEntry(
                id=f"JE-{uuid4().hex[:12].upper()}",
                timestamp=occurred_at,
                task_id=task_id,
                sequence=sequence,
                phase=phase,
                event=str(event or ""),
                status=str(status or ""),
                metadata=safe_metadata,
                fingerprint=fingerprint,
                previous_fingerprint=previous_fingerprint,
            )
        )

    def handle(self, event):
        """Project a privacy-safe Core EventBus event into the journal."""
        if getattr(event, "aggregate_type", "") != "RuntimeTask":
            return None
        payload = dict(getattr(event, "payload", {}) or {})
        task_id = str(payload.get("task_id") or getattr(event, "aggregate_id", ""))
        event_type = str(getattr(event, "event_type", "") or "")
        phase = phase_for_runtime_event(event_type, payload)
        status = str(payload.get("new_state") or event_status(event_type))
        metadata = {
            key: value
            for key, value in payload.items()
            if key in SAFE_METADATA_KEYS
        }
        return self.record(
            task_id,
            phase,
            event_type,
            status=status,
            metadata=metadata,
            timestamp=getattr(event, "occurred_at", ""),
        )

    def add_artifact(
        self,
        task_id,
        artifact_type,
        fingerprint,
        artifact_id="",
        verified=False,
        size=0,
        media_type="",
        sensitivity="protected",
    ):
        artifact = JournalArtifact(
            artifact_id=str(artifact_id or f"JA-{uuid4().hex[:12].upper()}"),
            task_id=str(task_id or ""),
            artifact_type=str(artifact_type or ""),
            fingerprint=str(fingerprint or ""),
            created_at=self.clock(),
            verified=bool(verified),
            size=max(0, int(size or 0)),
            media_type=str(media_type or ""),
            sensitivity=str(sensitivity or "protected"),
        )
        self.store.add_artifact(artifact)
        self.record(
            artifact.task_id,
            JournalPhase.EXECUTION,
            "ARTIFACT_VERIFIED" if artifact.verified else "ARTIFACT_CREATED",
            status="VERIFIED" if artifact.verified else "CREATED",
            metadata={"status": "verified" if artifact.verified else "created"},
        )
        return artifact

    def replay(self, task_id):
        entries = self.store.entries(task_id)
        errors = []
        previous = ""
        for expected_sequence, entry in enumerate(entries, start=1):
            if entry.sequence != expected_sequence:
                errors.append(f"SEQUENCE:{entry.sequence}")
            expected = entry_fingerprint(
                entry.task_id,
                entry.sequence,
                entry.phase.value,
                entry.event,
                entry.status,
                entry.metadata,
                previous,
            )
            if entry.previous_fingerprint != previous or entry.fingerprint != expected:
                errors.append(f"FINGERPRINT:{entry.sequence}")
            previous = entry.fingerprint
        return ReplayResult(str(task_id or ""), entries, not errors, tuple(errors))

    def explain(self, task_id):
        entries = self.store.entries(task_id)
        if not entries:
            return ExplainResult(str(task_id or ""), "Task journal not found.", (), "")
        reasons = []
        for entry in entries:
            reason = entry.metadata.get("reason") or entry.metadata.get("transition_reason")
            if reason:
                reasons.append(f"{entry.phase.value}:{entry.event}:{reason}")
            implementation = entry.metadata.get("selected_implementation")
            if implementation:
                reasons.append(f"DISCOVERY:selected:{implementation}")
        terminal = next(
            (entry for entry in reversed(entries) if entry.phase == JournalPhase.RESULT),
            entries[-1],
        )
        summary = (
            f"Task {task_id} recorded {len(entries)} decisions and ended "
            f"with {terminal.status or terminal.event}."
        )
        return ExplainResult(str(task_id or ""), summary, tuple(reasons), terminal.status)

    def explain_why(self, task_id):
        """Render the recorded causal path for terminal and waiting outcomes."""
        entries = self.store.entries(task_id)
        if not entries:
            return f"Task {task_id}\n  Journal not found"
        lines = [f"Task {task_id}"]
        selected = [
            entry
            for entry in entries
            if entry.event
            in {
                "CAPABILITY_SELECTED",
                "CONFIRMATION_REQUESTED",
                "RECOVERY_DECIDED",
                "VERIFICATION_SUCCESS",
                "STEP_FAILED",
                "TASK_RESULT",
                "TaskConfirmationRequired",
                "TaskResumed",
                "TaskFailed",
                "TaskCompleted",
                "TaskCancelled",
            }
        ]
        for entry in selected:
            operation = ".".join(
                part
                for part in (
                    str(entry.metadata.get("capability", "")),
                    str(entry.metadata.get("operation", "")),
                )
                if part
            )
            reason = entry.metadata.get("reason") or entry.metadata.get("transition_reason")
            detail = operation or str(reason or entry.status or "")
            suffix = f" ({detail})" if detail else ""
            lines.append(f"  -> {entry.event}{suffix}")
        return "\n".join(lines)

    def timeline(self, task_id):
        """Render a compact chronological task view for CLI diagnostics."""
        entries = self.store.entries(task_id)
        lines = [f"Task {task_id} Timeline"]
        for entry in entries:
            time_text = timeline_time(entry.timestamp)
            status = f" [{entry.status}]" if entry.status else ""
            lines.append(
                f"{time_text}  {entry.phase.value:<12}  {entry.event}{status}"
            )
        if not entries:
            lines.append("(no entries)")
        return "\n".join(lines)

    def tree(self, task_id):
        """Render phases and decisions as an ASCII tree."""
        entries = self.store.entries(task_id)
        lines = [f"Task {task_id}"]
        grouped = []
        phase_order = tuple(dict.fromkeys(entry.phase for entry in entries))
        for phase in phase_order:
            phase_entries = [entry for entry in entries if entry.phase == phase]
            if phase_entries:
                grouped.append((phase, phase_entries))
        for phase_index, (phase, phase_entries) in enumerate(grouped):
            phase_last = phase_index == len(grouped) - 1
            phase_branch = "`--" if phase_last else "|--"
            lines.append(f"{phase_branch} {phase.value}")
            child_prefix = "    " if phase_last else "|   "
            for entry_index, entry in enumerate(phase_entries):
                entry_last = entry_index == len(phase_entries) - 1
                entry_branch = "`--" if entry_last else "|--"
                operation = ".".join(
                    part
                    for part in (
                        str(entry.metadata.get("capability", "")),
                        str(entry.metadata.get("operation", "")),
                    )
                    if part
                )
                label = operation or entry.event
                status = f" [{entry.status}]" if entry.status else ""
                lines.append(f"{child_prefix}{entry_branch} {label}{status}")
        if not entries:
            lines.append("`-- (no entries)")
        return "\n".join(lines)

    def query(self, phase=None, event="", status="", task_id=""):
        task_ids = (str(task_id),) if task_id else self.store.task_ids()
        expected_phase = phase if isinstance(phase, JournalPhase) else (
            JournalPhase(str(phase)) if phase else None
        )
        return tuple(
            entry
            for current_task_id in task_ids
            for entry in self.store.entries(current_task_id)
            if (expected_phase is None or entry.phase == expected_phase)
            and (not event or entry.event == event)
            and (not status or entry.status == status)
        )

    def search(self, query, limit=20):
        """Search recent operational categories without inspecting raw content."""
        normalized = str(query or "").strip().lower()
        matcher = search_matcher(normalized)
        entries = [
            entry
            for task_id in self.store.task_ids()
            for entry in self.store.entries(task_id)
            if matcher(entry)
        ]
        entries.sort(key=lambda entry: (entry.timestamp, entry.task_id, entry.sequence), reverse=True)
        return JournalSearchResult(normalized, tuple(entries[: max(0, int(limit or 0))]))

    def to_json(self, task_id=""):
        task_ids = (str(task_id),) if task_id else self.store.task_ids()
        payload = {
            "schema_version": self.schema_version,
            "tasks": {
                current: [entry.to_dict() for entry in self.store.entries(current)]
                for current in task_ids
            },
            "artifacts": {
                current: [asdict(item) for item in self.store.artifacts(current)]
                for current in task_ids
            },
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def to_markdown(self, task_id=""):
        task_ids = (str(task_id),) if task_id else self.store.task_ids()
        lines = ["# Jarvis Execution Journal", ""]
        for current in task_ids:
            lines.extend([f"## Task `{current}`", "", "### Timeline", "", "```text"])
            lines.extend(self.timeline(current).splitlines())
            lines.extend(["```", "", "### Decision Tree", "", "```text"])
            lines.extend(self.tree(current).splitlines())
            lines.extend(["```", "", "### Explain Why", "", "```text"])
            lines.extend(self.explain_why(current).splitlines())
            lines.extend(["```", ""])
        return "\n".join(lines)

    def to_html(self, task_id=""):
        task_ids = (str(task_id),) if task_id else self.store.task_ids()
        sections = []
        for current in task_ids:
            sections.append(
                "<section>"
                f"<h2>Task <code>{html.escape(current)}</code></h2>"
                "<h3>Timeline</h3>"
                f"<pre>{html.escape(self.timeline(current))}</pre>"
                "<h3>Decision Tree</h3>"
                f"<pre>{html.escape(self.tree(current))}</pre>"
                "<h3>Explain Why</h3>"
                f"<pre>{html.escape(self.explain_why(current))}</pre>"
                "</section>"
            )
        return (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Jarvis Execution Journal</title>"
            "<style>body{font:14px system-ui;margin:32px;max-width:1100px}"
            "section{border-top:1px solid #ccc;padding:16px 0}"
            "pre{background:#f5f5f5;padding:12px;overflow:auto}"
            "code{font-family:ui-monospace,monospace}</style></head><body>"
            "<h1>Jarvis Execution Journal</h1>"
            + "".join(sections)
            + "</body></html>"
        )

    def export(self, path, task_id=""):
        """Export a redacted journal view selected by file extension."""
        target = Path(path)
        suffix = target.suffix.lower()
        if suffix == ".json":
            content = self.to_json(task_id)
        elif suffix in {".md", ".markdown"}:
            content = self.to_markdown(task_id)
        elif suffix in {".html", ".htm"}:
            content = self.to_html(task_id)
        else:
            raise ValueError("JOURNAL_EXPORT_FORMAT_UNSUPPORTED")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    @classmethod
    def from_json(cls, text):
        payload = json.loads(str(text or "{}"))
        if int(payload.get("schema_version", 0)) != cls.schema_version:
            raise ValueError("JOURNAL_SCHEMA_VERSION_UNSUPPORTED")
        journal = cls()
        for task_id, entries in dict(payload.get("tasks", {})).items():
            for entry_data in entries:
                entry = JournalEntry.from_dict(entry_data)
                if entry.task_id != task_id:
                    raise ValueError("JOURNAL_TASK_ID_MISMATCH")
                journal.store.append(entry)
        for task_id, artifacts in dict(payload.get("artifacts", {})).items():
            for artifact_data in artifacts:
                artifact = JournalArtifact(**artifact_data)
                if artifact.task_id != task_id:
                    raise ValueError("JOURNAL_TASK_ID_MISMATCH")
                journal.store.add_artifact(artifact)
        return journal


def sanitize_metadata(metadata):
    """Keep only operational metadata and reject likely PII values."""
    safe = {}
    for key, value in dict(metadata or {}).items():
        normalized_key = str(key or "").strip()
        lowered = normalized_key.lower()
        if normalized_key not in SAFE_METADATA_KEYS:
            continue
        if any(part in lowered for part in SENSITIVE_KEY_PARTS):
            continue
        safe_value = sanitize_value(value)
        if safe_value is not None:
            safe[normalized_key] = safe_value
    return safe


def sanitize_value(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, str):
        if EMAIL_PATTERN.search(value):
            return None
        return value[:256]
    if isinstance(value, (list, tuple)):
        return [item for item in (sanitize_value(item) for item in value) if item is not None]
    return None


def phase_for_runtime_event(event_type, payload):
    state = str(payload.get("new_state", ""))
    reason = str(payload.get("transition_reason", ""))
    source = str(payload.get("transition_source", ""))
    if state in {"PLANNING"} or "planner" in reason:
        return JournalPhase.PLAN
    if state == "VALIDATING" or "validation" in reason or "revalidated" in reason:
        return JournalPhase.VALIDATION
    if state == "OPTIMIZING" or "optimization" in reason:
        return JournalPhase.OPTIMIZATION
    if state == "WAIT_CONFIRM" or "Confirmation" in event_type:
        return JournalPhase.PERMISSION
    if source == "USER" and state == "RESUMING":
        return JournalPhase.CONVERSATION
    if state in {"RETRYING", "RESUMING", "PAUSED"}:
        return JournalPhase.RECOVERY
    if state == "VERIFYING" or "verification" in reason:
        return JournalPhase.VERIFICATION
    if state in {"COMPLETED", "SUCCESS", "FAILED", "CANCELLED", "PARTIAL_SUCCESS"}:
        return JournalPhase.RESULT
    return JournalPhase.EXECUTION


def event_status(event_type):
    if event_type.endswith("Completed"):
        return "COMPLETED"
    if event_type.endswith("Failed"):
        return "FAILED"
    if event_type.endswith("Cancelled"):
        return "CANCELLED"
    return ""


def timeline_time(timestamp):
    try:
        return datetime.fromisoformat(str(timestamp or "")).strftime("%H:%M:%S.%f")[:-3]
    except (TypeError, ValueError):
        return str(timestamp or "-")


def search_matcher(query):
    categories = {
        "failed": ("실패", "failed", "failure"),
        "retry": ("retry", "재시도"),
        "calendar": ("calendar", "캘린더", "일정"),
        "mail": ("gmail", "mail", "메일"),
        "oauth": ("oauth", "인증", "reauth", "auth"),
        "pause": ("pause", "paused", "중단", "일시정지"),
    }
    category = next(
        (
            name
            for name, aliases in categories.items()
            if any(alias in query for alias in aliases)
        ),
        "",
    )

    def matches(entry):
        searchable = " ".join(
            [
                entry.phase.value,
                entry.event,
                entry.status,
                *(str(value) for value in entry.metadata.values()),
            ]
        ).lower()
        if category == "failed":
            return entry.status == "FAILED" or "failed" in entry.event.lower()
        if category == "retry":
            return entry.phase == JournalPhase.RECOVERY and (
                "retry" in searchable or "backoff" in searchable
            )
        if category == "calendar":
            return entry.metadata.get("capability") == "calendar"
        if category == "mail":
            return entry.metadata.get("capability") == "mail"
        if category == "oauth":
            return any(token in searchable for token in ("oauth", "reauth", "auth"))
        if category == "pause":
            return entry.status == "PAUSED" or "paused" in searchable
        return bool(query) and query in searchable

    return matches


def entry_fingerprint(task_id, sequence, phase, event, status, metadata, previous):
    payload = {
        "task_id": task_id,
        "sequence": sequence,
        "phase": phase,
        "event": event,
        "status": status,
        "metadata": metadata,
        "previous_fingerprint": previous,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def journal_now():
    return datetime.now().isoformat(timespec="milliseconds")
