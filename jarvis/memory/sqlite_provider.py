"""SQLite repository for structured Jarvis memories."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from jarvis.memory.models import MemoryRecord, MemoryType


class MemoryRepository(Protocol):
    provider_name: str

    def upsert(self, record): ...
    def get(self, key, memory_type=None, session_id=""): ...
    def search(self, query="", memory_types=(), session_id="", limit=20): ...
    def delete(self, key, memory_type=None, session_id=""): ...
    def clear_working(self, session_id): ...
    def purge_expired(self, expires_before): ...


StructuredMemoryProvider = MemoryRepository


class SQLiteMemoryProvider:
    provider_name = "sqlite"

    def __init__(self, path="data/jarvis_memory.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        with self.session() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_provider TEXT NOT NULL DEFAULT '',
                    origin TEXT NOT NULL DEFAULT 'manual',
                    created_by TEXT NOT NULL DEFAULT 'user',
                    confidence REAL NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    expires_at TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(key, memory_type, scope, session_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_lookup "
                "ON memories(memory_type, session_id, key)"
            )
            ensure_column(connection, "memories", "source_provider", "TEXT NOT NULL DEFAULT ''")
            ensure_column(connection, "memories", "origin", "TEXT NOT NULL DEFAULT 'manual'")
            ensure_column(connection, "memories", "created_by", "TEXT NOT NULL DEFAULT 'user'")
            ensure_column(connection, "memories", "version", "INTEGER NOT NULL DEFAULT 1")
            ensure_column(connection, "memories", "expires_at", "TEXT NOT NULL DEFAULT ''")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_expiry "
                "ON memories(expires_at)"
            )

    def upsert(self, record):
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO memories (
                    id, key, value, memory_type, scope, session_id, source,
                    source_provider, origin, created_by, confidence, version,
                    expires_at, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key, memory_type, scope, session_id) DO UPDATE SET
                    value=excluded.value,
                    source=excluded.source,
                    source_provider=excluded.source_provider,
                    origin=excluded.origin,
                    created_by=excluded.created_by,
                    confidence=excluded.confidence,
                    version=memories.version + 1,
                    expires_at=excluded.expires_at,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    record.id,
                    record.key,
                    record.value,
                    record.memory_type.value,
                    record.scope,
                    record.session_id,
                    record.source,
                    record.source_provider,
                    record.origin,
                    record.created_by,
                    record.confidence,
                    record.version,
                    record.expires_at,
                    json.dumps(record.metadata, ensure_ascii=False, sort_keys=True),
                    record.created_at,
                    record.updated_at,
                ),
            )
        return self.get(
            record.key,
            memory_type=record.memory_type,
            session_id=record.session_id,
        )

    def get(self, key, memory_type=None, session_id=""):
        clauses = ["key = ?"]
        values = [str(key)]
        if memory_type is not None:
            clauses.append("memory_type = ?")
            values.append(normalize_type(memory_type).value)
        if session_id:
            clauses.append("session_id = ?")
            values.append(str(session_id))
        query = (
            "SELECT * FROM memories WHERE "
            + " AND ".join(clauses)
            + " ORDER BY updated_at DESC LIMIT 1"
        )
        with self.session() as connection:
            row = connection.execute(query, values).fetchone()
        return row_to_record(row) if row is not None else None

    def search(self, query="", memory_types=(), session_id="", limit=20):
        clauses = []
        values = []
        normalized_query = str(query or "").strip()
        if normalized_query:
            clauses.append("(key LIKE ? OR value LIKE ?)")
            pattern = f"%{normalized_query}%"
            values.extend([pattern, pattern])
        normalized_types = tuple(normalize_type(item).value for item in memory_types)
        if normalized_types:
            placeholders = ",".join("?" for _ in normalized_types)
            clauses.append(f"memory_type IN ({placeholders})")
            values.extend(normalized_types)
        if session_id:
            clauses.append("(session_id = ? OR session_id = '')")
            values.append(str(session_id))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, int(limit)))
        with self.session() as connection:
            rows = connection.execute(
                f"SELECT * FROM memories{where} ORDER BY updated_at DESC LIMIT ?",
                values,
            ).fetchall()
        return [row_to_record(row) for row in rows]

    def delete(self, key, memory_type=None, session_id=""):
        clauses = ["key = ?"]
        values = [str(key)]
        if memory_type is not None:
            clauses.append("memory_type = ?")
            values.append(normalize_type(memory_type).value)
        if session_id:
            clauses.append("session_id = ?")
            values.append(str(session_id))
        with self.session() as connection:
            cursor = connection.execute(
                f"DELETE FROM memories WHERE {' AND '.join(clauses)}",
                values,
            )
        return cursor.rowcount

    def clear_working(self, session_id):
        with self.session() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE memory_type = ? AND session_id = ?",
                (MemoryType.WORKING.value, str(session_id)),
            )
        return cursor.rowcount

    def purge_expired(self, expires_before):
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM memories "
                "WHERE expires_at != '' AND expires_at <= ?",
                (str(expires_before),),
            ).fetchall()
            connection.execute(
                "DELETE FROM memories WHERE expires_at != '' AND expires_at <= ?",
                (str(expires_before),),
            )
        return [row_to_record(row) for row in rows]


def normalize_type(value):
    return value if isinstance(value, MemoryType) else MemoryType(str(value))


def ensure_column(connection, table, column, definition):
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def row_to_record(row):
    return MemoryRecord(
        id=row["id"],
        key=row["key"],
        value=row["value"],
        memory_type=MemoryType(row["memory_type"]),
        scope=row["scope"],
        session_id=row["session_id"],
        source=row["source"],
        source_provider=row["source_provider"],
        origin=row["origin"],
        created_by=row["created_by"],
        confidence=float(row["confidence"]),
        version=int(row["version"]),
        expires_at=row["expires_at"],
        metadata=json.loads(row["metadata_json"] or "{}"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
