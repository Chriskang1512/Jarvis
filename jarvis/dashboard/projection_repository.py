"""Independent repositories for rebuildable Dashboard read models."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Protocol

from .projection_serialization import session_from_dict, session_to_dict


class DashboardProjectionRepository(Protocol):
    def save_session(self, session): ...
    def get_session(self, session_id): ...
    def running_sessions(self): ...
    def recent_sessions(self, limit=20): ...
    def append_event(self, event): ...
    def events_after(self, sequence=0): ...
    def save_snapshot(self, sequence, sessions): ...
    def latest_snapshot(self): ...
    def reset_sessions(self): ...


class InMemoryDashboardProjectionRepository:
    def __init__(self):
        self.sessions = {}
        self.events = []
        self.snapshot = None
        self._lock = RLock()

    def save_session(self, session):
        with self._lock:
            self.sessions[session.session_id] = session
        return session

    def get_session(self, session_id):
        with self._lock:
            return self.sessions.get(str(session_id))

    def running_sessions(self):
        with self._lock:
            return tuple(
                item for item in self.sessions.values()
                if item.status not in {"Completed", "Failed", "Cancelled"}
            )

    def recent_sessions(self, limit=20):
        with self._lock:
            return tuple(sorted(
                self.sessions.values(), key=lambda item: item.started_at, reverse=True
            )[: max(1, int(limit))])

    def append_event(self, event):
        with self._lock:
            self.events.append(dict(event))

    def events_after(self, sequence=0):
        with self._lock:
            return tuple(item for item in self.events if item["eventSequence"] > sequence)

    def save_snapshot(self, sequence, sessions):
        with self._lock:
            self.snapshot = (int(sequence), tuple(sessions))

    def latest_snapshot(self):
        with self._lock:
            return self.snapshot

    def reset_sessions(self):
        with self._lock:
            self.sessions.clear()


class SQLiteDashboardProjectionRepository(InMemoryDashboardProjectionRepository):
    def __init__(self, path="data/jarvis_memory.db"):
        super().__init__()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()
        self._restore()

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        with self.connection() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS dashboard_projection_sessions(
                    session_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                    started_at TEXT NOT NULL, projection_json TEXT NOT NULL)"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS dashboard_projection_events(
                    event_sequence INTEGER PRIMARY KEY, event_json TEXT NOT NULL)"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS dashboard_projection_snapshots(
                    snapshot_id INTEGER PRIMARY KEY CHECK(snapshot_id=1),
                    event_sequence INTEGER NOT NULL, snapshot_json TEXT NOT NULL)"""
            )

    def _restore(self):
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT projection_json FROM dashboard_projection_sessions"
            ).fetchall()
            events = connection.execute(
                "SELECT event_json FROM dashboard_projection_events ORDER BY event_sequence"
            ).fetchall()
            snapshot = connection.execute(
                "SELECT event_sequence,snapshot_json FROM dashboard_projection_snapshots WHERE snapshot_id=1"
            ).fetchone()
        for row in rows:
            session = session_from_dict(json.loads(row[0]))
            self.sessions[session.session_id] = session
        self.events = [json.loads(row[0]) for row in events]
        if snapshot:
            self.snapshot = (
                int(snapshot[0]),
                tuple(session_from_dict(item) for item in json.loads(snapshot[1])),
            )

    def save_session(self, session):
        super().save_session(session)
        with self.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO dashboard_projection_sessions VALUES(?,?,?,?)",
                (session.session_id, session.status, session.started_at.isoformat(),
                 json.dumps(session_to_dict(session), ensure_ascii=False, sort_keys=True)),
            )
        return session

    def append_event(self, event):
        super().append_event(event)
        with self.connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO dashboard_projection_events VALUES(?,?)",
                (event["eventSequence"], json.dumps(event, ensure_ascii=False, sort_keys=True)),
            )

    def save_snapshot(self, sequence, sessions):
        super().save_snapshot(sequence, sessions)
        payload = [session_to_dict(item) for item in sessions]
        with self.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO dashboard_projection_snapshots VALUES(1,?,?)",
                (int(sequence), json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            )

    def reset_sessions(self):
        super().reset_sessions()
        with self.connection() as connection:
            connection.execute("DELETE FROM dashboard_projection_sessions")
