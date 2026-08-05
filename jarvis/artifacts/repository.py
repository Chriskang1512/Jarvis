"""Provider-independent artifact repositories and lifecycle operations."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from typing import Protocol

from .models import ArtifactStatus, utc_now
from .serialization import artifact_from_dict, artifact_to_dict


CURRENT_ARTIFACT_DB_SCHEMA_VERSION = 1
DEFAULT_MAX_RELATIONSHIP_DEPTH = 20


class ArtifactRepository(Protocol):
    def save(self, artifact): ...
    def get(self, artifact_id, include_deleted=False): ...
    def list(self, include_deleted=False, limit=100): ...
    def search_metadata(self, **criteria): ...
    def link(self, parent_id, child_id): ...
    def archive(self, artifact_id): ...
    def soft_delete(self, artifact_id): ...
    def parent(self, artifact_id): ...
    def children(self, artifact_id): ...


class InMemoryArtifactRepository:
    def __init__(self, max_relationship_depth=DEFAULT_MAX_RELATIONSHIP_DEPTH):
        self.records = {}
        self.max_relationship_depth = max(1, int(max_relationship_depth))

    def save(self, artifact):
        existing = self.records.get(artifact.artifact_id)
        if existing and existing.checksum == artifact.checksum:
            return existing, False
        self.records[artifact.artifact_id] = artifact
        return artifact, existing is None

    def get(self, artifact_id, include_deleted=False):
        artifact = self.records.get(str(artifact_id))
        if artifact and (include_deleted or artifact.status != ArtifactStatus.DELETED):
            return artifact
        return None

    def list(self, include_deleted=False, limit=100):
        records = sorted(
            self.records.values(), key=lambda item: item.updated_at, reverse=True
        )
        if not include_deleted:
            records = [item for item in records if item.status != ArtifactStatus.DELETED]
        return records[: max(1, int(limit))]

    def search_metadata(self, limit=50, include_deleted=False, **criteria):
        records = self.list(include_deleted=include_deleted, limit=max(limit * 5, 100))
        return [item for item in records if matches(item, criteria)][:limit]

    def link(self, parent_id, child_id):
        parent = self.get(parent_id)
        child = self.get(child_id)
        if not parent or not child:
            raise KeyError("Parent and child artifacts must exist.")
        if parent.artifact_id == child.artifact_id:
            raise ValueError("An artifact cannot be its own parent.")
        if creates_cycle(self, parent.artifact_id, child.artifact_id):
            raise ValueError("Artifact relationship would create a cycle.")
        if relationship_depth(self, parent.artifact_id) + subtree_depth(
            self, child.artifact_id
        ) > self.max_relationship_depth:
            raise ValueError(
                "Artifact relationship exceeds maximum depth "
                f"{self.max_relationship_depth}."
            )
        now = utc_now()
        parent = replace(
            parent,
            child_artifact_ids=tuple(sorted(set((*parent.child_artifact_ids, child.artifact_id)))),
            status=ArtifactStatus.UPDATED,
            updated_at=now,
        )
        child = replace(
            child,
            parent_artifact_id=parent.artifact_id,
            status=ArtifactStatus.UPDATED,
            updated_at=now,
        )
        self.records[parent.artifact_id] = parent
        self.records[child.artifact_id] = child
        return parent, child

    def archive(self, artifact_id):
        return self._change_status(artifact_id, ArtifactStatus.ARCHIVED)

    def soft_delete(self, artifact_id):
        return self._change_status(artifact_id, ArtifactStatus.DELETED)

    def parent(self, artifact_id):
        artifact = self.get(artifact_id, include_deleted=True)
        if not artifact or not artifact.parent_artifact_id:
            return None
        return self.get(artifact.parent_artifact_id, include_deleted=True)

    def children(self, artifact_id):
        artifact = self.get(artifact_id, include_deleted=True)
        if not artifact:
            return ()
        return tuple(
            item
            for child_id in artifact.child_artifact_ids
            if (item := self.get(child_id, include_deleted=True)) is not None
        )

    def _change_status(self, artifact_id, status):
        artifact = self.get(artifact_id, include_deleted=True)
        if not artifact:
            raise KeyError(str(artifact_id))
        artifact = replace(artifact, status=status, updated_at=utc_now())
        self.records[artifact.artifact_id] = artifact
        return artifact


class SQLiteArtifactRepository(InMemoryArtifactRepository):
    """SQLite persistence with the in-memory API and explicit schema version."""

    def __init__(
        self,
        path="data/jarvis_memory.db",
        max_relationship_depth=DEFAULT_MAX_RELATIONSHIP_DEPTH,
    ):
        super().__init__(max_relationship_depth=max_relationship_depth)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()
        for artifact in self._load_all():
            self.records[artifact.artifact_id] = artifact

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
            SQLiteArtifactMigrationRunner().migrate(connection)

    def save(self, artifact):
        stored, created = super().save(artifact)
        self._persist(stored)
        return stored, created

    def link(self, parent_id, child_id):
        parent, child = super().link(parent_id, child_id)
        self._persist(parent)
        self._persist(child)
        return parent, child

    def _change_status(self, artifact_id, status):
        artifact = super()._change_status(artifact_id, status)
        self._persist(artifact)
        return artifact

    def _persist(self, artifact):
        payload = artifact_to_dict(artifact)
        with self.session() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO artifacts(
                    artifact_id,artifact_type,status,title,goal_id,execution_id,
                    searchable_text,artifact_json,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    artifact.artifact_id, artifact.artifact_type.value,
                    artifact.status.value, artifact.title, artifact.source_goal_id,
                    artifact.source_execution_id, searchable_text(artifact),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    artifact.updated_at.isoformat(),
                ),
            )

    def _load_all(self):
        with self.session() as connection:
            rows = connection.execute("SELECT artifact_json FROM artifacts").fetchall()
        return [artifact_from_dict(json.loads(row[0])) for row in rows]


def matches(artifact, criteria):
    query = str(criteria.get("query", "")).casefold()
    if query and query not in searchable_text(artifact):
        return False
    comparisons = {
        "artifact_id": artifact.artifact_id,
        "artifact_type": artifact.artifact_type.value,
        "goal_id": artifact.source_goal_id,
        "execution_id": artifact.source_execution_id,
        "provider": artifact.provider,
    }
    for key, actual in comparisons.items():
        expected = criteria.get(key)
        if expected and str(actual).casefold() != str(getattr(expected, "value", expected)).casefold():
            return False
    tag = criteria.get("tag")
    return not tag or str(tag).casefold() in {item.casefold() for item in artifact.tags}


def searchable_text(artifact):
    return " ".join(
        (artifact.artifact_id, artifact.title, artifact.summary,
         artifact.artifact_type.value, artifact.source_goal_id,
         artifact.source_execution_id, artifact.provider, *artifact.tags)
    ).casefold()


def creates_cycle(repository, parent_id, child_id):
    current = repository.get(parent_id, include_deleted=True)
    while current and current.parent_artifact_id:
        if current.parent_artifact_id == child_id:
            return True
        current = repository.get(current.parent_artifact_id, include_deleted=True)
    return False


def relationship_depth(repository, artifact_id):
    """Return one-based depth from the root for an existing artifact."""
    depth = 1
    current = repository.get(artifact_id, include_deleted=True)
    visited = set()
    while current and current.parent_artifact_id:
        if current.artifact_id in visited:
            raise ValueError("Artifact relationship contains a cycle.")
        visited.add(current.artifact_id)
        depth += 1
        current = repository.get(
            current.parent_artifact_id, include_deleted=True
        )
    return depth


def subtree_depth(repository, artifact_id):
    """Return the longest one-based descendant path."""
    artifact = repository.get(artifact_id, include_deleted=True)
    if not artifact or not artifact.child_artifact_ids:
        return 1
    return 1 + max(
        subtree_depth(repository, child_id)
        for child_id in artifact.child_artifact_ids
    )


class SQLiteArtifactMigrationRunner:
    """Run ordered Artifact schema migrations and reject unknown layouts."""

    def migrate(self, connection):
        connection.execute(
            """CREATE TABLE IF NOT EXISTS artifact_schema_versions (
                component TEXT PRIMARY KEY, version INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
        )
        row = connection.execute(
            "SELECT version FROM artifact_schema_versions "
            "WHERE component='artifact_manager'"
        ).fetchone()
        version = int(row[0]) if row else 0
        if version > CURRENT_ARTIFACT_DB_SCHEMA_VERSION:
            raise RuntimeError(
                "Artifact database schema is newer than this runtime: "
                f"{version} > {CURRENT_ARTIFACT_DB_SCHEMA_VERSION}"
            )
        while version < CURRENT_ARTIFACT_DB_SCHEMA_VERSION:
            migration = getattr(self, f"migrate_{version}_to_{version + 1}")
            migration(connection)
            version += 1
            connection.execute(
                """INSERT INTO artifact_schema_versions(
                    component, version, updated_at
                ) VALUES('artifact_manager', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(component) DO UPDATE SET
                    version=excluded.version,
                    updated_at=CURRENT_TIMESTAMP""",
                (version,),
            )
        self.validate_schema(connection)

    @staticmethod
    def migrate_0_to_1(connection):
        connection.execute(
            """CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY, artifact_type TEXT NOT NULL,
                status TEXT NOT NULL, title TEXT NOT NULL, goal_id TEXT NOT NULL,
                execution_id TEXT NOT NULL, searchable_text TEXT NOT NULL,
                artifact_json TEXT NOT NULL, updated_at TEXT NOT NULL)"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_artifacts_lookup "
            "ON artifacts(artifact_type,status,goal_id,execution_id,updated_at)"
        )

    @staticmethod
    def validate_schema(connection):
        required = {
            "artifact_id",
            "artifact_type",
            "status",
            "title",
            "goal_id",
            "execution_id",
            "searchable_text",
            "artifact_json",
            "updated_at",
        }
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(artifacts)"
            ).fetchall()
        }
        missing = required - columns
        if missing:
            raise RuntimeError(
                "Artifact database schema is inconsistent; missing columns: "
                f"{', '.join(sorted(missing))}"
            )
