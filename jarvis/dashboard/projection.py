"""Event-only Dashboard Projection engine; Runtime remains source of truth."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from jarvis.runtime.state import RuntimeState
from .projection_models import (
    NodeView, ProjectionHealth, ProjectionHealthStatus, ProjectionVersion,
    RuntimeSessionView, TimelineView,
)


TERMINAL = {"Completed", "Failed", "Cancelled"}


class DashboardProjectionEngine:
    def __init__(self, repository, *, snapshot_interval=100, runtime_version="v1.5"):
        self.repository = repository
        self.snapshot_interval = max(1, int(snapshot_interval))
        self.runtime_version = runtime_version
        self.current_runtime_state = RuntimeState.IDLE
        self.sequence = max(
            (item.get("eventSequence", 0) for item in repository.events_after(0)),
            default=0,
        )
        projected_sequence = max(
            (
                item.last_event_sequence
                for item in repository.recent_sessions(limit=1000)
            ),
            default=self.sequence,
        )
        lag = max(0, self.sequence - projected_sequence)
        self.health = ProjectionHealth(
            ProjectionHealthStatus.LAG if lag else ProjectionHealthStatus.HEALTHY,
            projected_sequence,
            self.sequence,
            lag,
        )
        self._lock = RLock()

    def apply(self, event_type, payload=None, occurred_at=None):
        with self._lock:
            self.sequence += 1
            sequence = self.sequence
            event = {
                "eventSequence": sequence,
                "eventType": str(event_type),
                "occurredAt": occurred_at or datetime.now(timezone.utc).isoformat(),
                "payload": safe_payload(payload or {}),
            }
            try:
                self.repository.append_event(event)
                session = self._project(event)
                self.health = ProjectionHealth(
                    ProjectionHealthStatus.HEALTHY, sequence, sequence, 0
                )
                if sequence % self.snapshot_interval == 0 or (
                    session and session.status in TERMINAL
                ):
                    self.repository.save_snapshot(
                        sequence, self.repository.recent_sessions(limit=1000)
                    )
                return event, session
            except Exception as error:
                self.health = ProjectionHealth(
                    ProjectionHealthStatus.FAILED,
                    sequence - 1,
                    sequence,
                    1,
                    error_type=type(error).__name__,
                )
                raise

    def _project(self, event):
        payload = event["payload"]
        name = event["eventType"]
        lowered = name.casefold()
        self.current_runtime_state = runtime_state_for_event(
            lowered, self.current_runtime_state
        )
        session_id = str(
            payload.get("session_id") or payload.get("sessionId") or ""
        )
        if not session_id:
            return None
        occurred_at = datetime.fromisoformat(event["occurredAt"].replace("Z", "+00:00"))
        session = self.repository.get_session(session_id) or RuntimeSessionView(
            session_id=session_id,
            goal=str(payload.get("goal") or payload.get("goal_id") or ""),
            started_at=occurred_at,
            current_runtime_state=RuntimeState.PLANNING,
            projection_version=self.version(),
        )
        nodes = dict(session.nodes)
        node_id = str(payload.get("node_id") or payload.get("nodeId") or "")
        node = nodes.get(node_id) if node_id else None
        changes = {"last_event_sequence": event["eventSequence"], "projection_version": self.version()}

        if "session_created" in lowered:
            changes.update(status="Running", execution_status="Running", current_runtime_state=RuntimeState.EXECUTING)
        elif "planner" in lowered and ("started" in lowered or "planning" in lowered):
            changes.update(planner_status="Running", current_runtime_state=RuntimeState.PLANNING)
        elif "snapshot_verified" in lowered or (
            "graph" in lowered and ("built" in lowered or "planned" in lowered)
        ):
            changes["planner_status"] = "Complete"
        elif "node_ready" in lowered and node_id:
            nodes[node_id] = replace(node or NodeView(node_id), status="Ready", ability=str(payload.get("capability_id") or ""))
        elif "node_started" in lowered and node_id:
            nodes[node_id] = replace(
                node or NodeView(node_id), status="Running", started_at=occurred_at,
                provider=str(payload.get("provider_id") or ""), ability=str(payload.get("capability_id") or ""),
            )
            changes.update(current_node=node_id, execution_status="Running", current_runtime_state=RuntimeState.EXECUTING)
        elif ("node_completed" in lowered or "node_skipped" in lowered) and node_id:
            nodes[node_id] = replace(node or NodeView(node_id), status="Skipped" if "skipped" in lowered else "Completed", finished_at=occurred_at)
            changes["current_node"] = ""
        elif "retry" in lowered:
            changes.update(retry_count=session.retry_count + (1 if "started" in lowered else 0), current_runtime_state=RuntimeState.EXECUTING)
            if node_id:
                nodes[node_id] = replace(node or NodeView(node_id), status="Retrying", retry_count=(node.retry_count if node else 0) + 1)
        elif "permission" in lowered:
            waiting = any(word in lowered for word in ("requested", "required", "waiting"))
            changes.update(waiting_permission=waiting, current_runtime_state=RuntimeState.WAITING_PERMISSION if waiting else RuntimeState.EXECUTING)
        elif "verification_started" in lowered or "goal_verification_started" in lowered:
            changes.update(verification_status="Running", current_runtime_state=RuntimeState.VERIFYING)
        elif "verification_passed" in lowered:
            changes.update(verification_status="Passed", current_runtime_state=RuntimeState.EXECUTING)
        elif "verification_failed" in lowered:
            changes["verification_status"] = "Failed"
        elif "memory_saved" in lowered or "memorypersisted" in lowered:
            changes["memory_status"] = "Saved"
            memory_id = str(payload.get("memory_record_id") or "")
            if node_id and memory_id:
                nodes[node_id] = replace(node or NodeView(node_id), memory_ids=tuple(sorted(set((*((node.memory_ids) if node else ()), memory_id)))))
        elif "artifacts_captured" in lowered or "artifactcreated" in lowered:
            changes["artifact_status"] = "Saved"
            for item in payload.get("artifacts", ()):
                artifact_node_id = str(item.get("node_id") or "")
                artifact_id = str(item.get("artifact_id") or "")
                if artifact_node_id and artifact_id:
                    artifact_node = nodes.get(artifact_node_id)
                    prior_ids = artifact_node.artifact_ids if artifact_node else ()
                    nodes[artifact_node_id] = replace(
                        artifact_node or NodeView(artifact_node_id),
                        artifact_ids=tuple(
                            sorted(set((*prior_ids, artifact_id)))
                        ),
                    )
        elif "session_completed" in lowered:
            outcome = str(
                (payload.get("execution_summary") or {}).get("outcome")
                or payload.get("outcome")
                or "Succeeded"
            )
            failed = outcome not in {"Succeeded", "Partial"}
            changes.update(
                status="Failed" if failed else "Completed",
                execution_status="Failed" if failed else "Completed",
                completed_at=occurred_at,
                current_runtime_state=(
                    RuntimeState.FAILED if failed else RuntimeState.COMPLETED
                ),
                current_node="",
            )
        elif "session_failed" in lowered:
            changes.update(status="Failed", execution_status="Failed", completed_at=occurred_at, current_runtime_state=RuntimeState.FAILED, current_node="")

        timeline = TimelineView(
            event["eventSequence"], name, occurred_at, session_id, node_id,
            str(payload.get("status") or payload.get("state") or ""),
            timeline_details(payload),
        )
        changes["nodes"] = nodes
        changes["timeline"] = (*session.timeline, timeline)
        session = replace(session, **changes)
        return self.repository.save_session(session)

    def version(self):
        return ProjectionVersion("runtime-sessions", runtime_version=self.runtime_version)

    def statistics(self):
        sessions = self.repository.recent_sessions(limit=1000)
        return {
            "total": len(sessions),
            "running": sum(item.status not in TERMINAL for item in sessions),
            "completed": sum(item.status == "Completed" for item in sessions),
            "failed": sum(item.status == "Failed" for item in sessions),
            "lastEventSequence": self.sequence,
            "currentRuntimeState": self.current_runtime_state.value,
        }

    def rebuild(self):
        events = self.repository.events_after(0)
        self.health = ProjectionHealth(ProjectionHealthStatus.REBUILDING, 0, len(events), len(events))
        self.repository.reset_sessions()
        for event in events:
            self._project(event)
        self.sequence = max(
            (item["eventSequence"] for item in events), default=0
        )
        self.repository.save_snapshot(
            self.sequence, self.repository.recent_sessions(limit=1000)
        )
        self.health = ProjectionHealth(
            ProjectionHealthStatus.HEALTHY,
            self.sequence,
            self.sequence,
            0,
        )
        return len(events)


class SafeDashboardProjectionHandler:
    """Subscriber boundary that cannot fail Runtime execution."""

    def __init__(self, engine, publish=None):
        self.engine = engine
        self.publish = publish
        self.failure_count = 0

    def handle_event(self, event):
        event_type = getattr(event, "event_type", getattr(event, "name", type(event).__name__))
        raw = event.to_dict() if hasattr(event, "to_dict") else getattr(event, "__dict__", {})
        if isinstance(raw, dict) and isinstance(raw.get("payload"), dict):
            payload = dict(raw["payload"])
            payload.setdefault("aggregate_id", raw.get("aggregate_id", ""))
            occurred_at = raw.get("occurred_at") or None
        else:
            payload = raw
            occurred_at = None
        try:
            projected_event, session = self.engine.apply(
                event_type, payload, occurred_at=occurred_at
            )
            if self.publish:
                self.publish(projected_event, session, self.engine.statistics())
            return session
        except Exception:
            self.failure_count += 1
            return None


def safe_payload(value):
    if isinstance(value, dict):
        return {str(key): safe_payload(item) for key, item in value.items() if str(key) not in {"raw_response", "access_token", "refresh_token"}}
    if isinstance(value, (list, tuple)):
        return [safe_payload(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def timeline_details(payload):
    allowed = ("graph_id", "snapshot_id", "capability_id", "provider_id", "attempt_number", "retry_count", "artifact_count")
    return {key: payload[key] for key in allowed if key in payload}


def runtime_state_for_event(name, current):
    if "listen" in name or "stt" in name:
        return RuntimeState.LISTENING
    if "planner" in name:
        return RuntimeState.PLANNING
    if "thinking" in name:
        return RuntimeState.THINKING
    if "verification" in name:
        return RuntimeState.VERIFYING
    if "permission" in name and any(
        item in name for item in ("requested", "required", "waiting")
    ):
        return RuntimeState.WAITING_PERMISSION
    if "node_" in name or "session_created" in name:
        return RuntimeState.EXECUTING
    if "tts" in name:
        return RuntimeState.SPEAKING if "started" in name else RuntimeState.IDLE
    if "session_completed" in name:
        return RuntimeState.COMPLETED
    if "session_failed" in name or "failed" in name:
        return RuntimeState.FAILED
    return current
