"""Provider-independent repositories for execution memory."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from .serialization import record_from_dict, record_to_dict

CURRENT_SQLITE_SCHEMA_VERSION = 1
SCHEMA_COMPONENT = "execution_memory"


class ExecutionMemoryRepository(Protocol):
    def add(self, record): ...
    def get(self, record_id): ...
    def get_by_execution(self, execution_id, summary_version=1): ...
    def list(self, limit=100): ...
    def search_metadata(self, query="", history_types=(), limit=20): ...


class InMemoryExecutionMemoryRepository:
    def __init__(self):
        self.records = {}
        self.unique = {}

    def add(self, record):
        existing_id = self.unique.get(record.unique_key)
        if existing_id:
            return self.records[existing_id], False
        self.records[record.record_id] = record
        self.unique[record.unique_key] = record.record_id
        return record, True

    def get(self, record_id):
        return self.records.get(str(record_id))

    def get_by_execution(self, execution_id, summary_version=1):
        record_id = self.unique.get(f"{execution_id}:{summary_version}")
        return self.records.get(record_id) if record_id else None

    def list(self, limit=100):
        return sorted(
            self.records.values(),
            key=lambda item: item.created_at,
            reverse=True,
        )[: max(1, int(limit))]

    def search_metadata(self, query="", history_types=(), limit=20):
        query = str(query or "").casefold()
        types = {str(getattr(item, "value", item)) for item in history_types}
        results = []
        for record in self.list(limit=max(limit * 5, 100)):
            if types and not any(
                entry.history_type.value in types
                for entry in record.histories
            ):
                continue
            searchable = " ".join(
                (
                    record.goal_id,
                    record.goal_signature,
                    record.outcome,
                    *record.tags,
                    *(
                        f"{entry.capability_id} {entry.status}"
                        for entry in record.histories
                    ),
                )
            ).casefold()
            if not query or query in searchable:
                results.append(record)
            if len(results) >= limit:
                break
        return results


class SQLiteExecutionMemoryRepository:
    provider_name = "sqlite"

    def __init__(self, path="data/jarvis_memory.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def session(self):
        connection = sqlite3.connect(self.path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        with self.session() as connection:
            SQLiteExecutionMemoryMigrationRunner().migrate(connection)

    def add(self, record):
        payload = record_to_dict(record)
        searchable = searchable_text(record)
        with self.session() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO execution_memories (
                    record_id, source_execution_id, summary_version,
                    schema_version, goal_id, session_id, graph_id, outcome,
                    searchable_text, record_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.source_execution_id,
                    record.summary_version,
                    record.schema_version,
                    record.goal_id,
                    record.session_id,
                    record.graph_id,
                    record.outcome,
                    searchable,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    record.created_at.isoformat(),
                ),
            )
        return self.get_by_execution(
            record.source_execution_id, record.summary_version
        ), bool(cursor.rowcount)

    def get(self, record_id):
        with self.session() as connection:
            row = connection.execute(
                "SELECT record_json FROM execution_memories "
                "WHERE record_id = ?",
                (str(record_id),),
            ).fetchone()
        return record_from_dict(json.loads(row[0])) if row else None

    def get_by_execution(self, execution_id, summary_version=1):
        with self.session() as connection:
            row = connection.execute(
                "SELECT record_json FROM execution_memories "
                "WHERE source_execution_id = ? AND summary_version = ?",
                (str(execution_id), int(summary_version)),
            ).fetchone()
        return record_from_dict(json.loads(row[0])) if row else None

    def list(self, limit=100):
        with self.session() as connection:
            rows = connection.execute(
                "SELECT record_json FROM execution_memories "
                "ORDER BY created_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [record_from_dict(json.loads(row[0])) for row in rows]

    def search_metadata(self, query="", history_types=(), limit=20):
        clauses = []
        values = []
        if query:
            clauses.append("searchable_text LIKE ?")
            values.append(f"%{str(query).casefold()}%")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, int(limit) * 5))
        with self.session() as connection:
            rows = connection.execute(
                "SELECT record_json FROM execution_memories"
                f"{where} ORDER BY created_at DESC LIMIT ?",
                values,
            ).fetchall()
        records = [record_from_dict(json.loads(row[0])) for row in rows]
        types = {str(getattr(item, "value", item)) for item in history_types}
        if types:
            records = [
                record
                for record in records
                if any(
                    entry.history_type.value in types
                    for entry in record.histories
                )
            ]
        return records[: max(1, int(limit))]


def searchable_text(record):
    return " ".join(
        (
            record.goal_id,
            record.goal_signature,
            record.outcome,
            *record.tags,
            *(
                f"{entry.history_type.value} {entry.capability_id} "
                f"{entry.status}"
                for entry in record.histories
            ),
        )
    ).casefold()


class SQLiteExecutionMemoryMigrationRunner:
    """Apply ordered schema migrations or fail fast on an unknown database."""

    def migrate(self, connection):
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_memory_schema_versions (
                component TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        row = connection.execute(
            "SELECT version FROM execution_memory_schema_versions "
            "WHERE component = ?",
            (SCHEMA_COMPONENT,),
        ).fetchone()
        version = int(row[0]) if row else 0
        if version > CURRENT_SQLITE_SCHEMA_VERSION:
            raise RuntimeError(
                "Execution Memory database schema is newer than this runtime: "
                f"{version} > {CURRENT_SQLITE_SCHEMA_VERSION}"
            )
        while version < CURRENT_SQLITE_SCHEMA_VERSION:
            migration = getattr(self, f"migrate_{version}_to_{version + 1}")
            migration(connection)
            version += 1
            connection.execute(
                """
                INSERT INTO execution_memory_schema_versions (
                    component, version, updated_at
                ) VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(component) DO UPDATE SET
                    version = excluded.version,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (SCHEMA_COMPONENT, version),
            )
        self.validate_schema(connection)

    @staticmethod
    def migrate_0_to_1(connection):
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_memories (
                record_id TEXT PRIMARY KEY,
                source_execution_id TEXT NOT NULL,
                summary_version INTEGER NOT NULL,
                schema_version INTEGER NOT NULL,
                goal_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                graph_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                searchable_text TEXT NOT NULL,
                record_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(source_execution_id, summary_version)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_memory_search "
            "ON execution_memories(goal_id, outcome, created_at)"
        )

    @staticmethod
    def validate_schema(connection):
        required = {
            "record_id",
            "source_execution_id",
            "summary_version",
            "schema_version",
            "goal_id",
            "session_id",
            "graph_id",
            "outcome",
            "searchable_text",
            "record_json",
            "created_at",
        }
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(execution_memories)"
            ).fetchall()
        }
        missing = required - columns
        if missing:
            raise RuntimeError(
                "Execution Memory database schema is inconsistent; "
                f"missing columns: {', '.join(sorted(missing))}"
            )
