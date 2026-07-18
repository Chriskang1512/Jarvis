import json
from pathlib import Path
from typing import Protocol

from jarvis.abilities.native.memory.models import MemoryEntry, memory_entry_from_dict
from jarvis.abilities.result import AbilityHealth
from jarvis.debug_trace import trace_event


class MemoryStorage(Protocol):
    """Storage provider contract for Memory Ability."""

    provider_name: str

    def upsert(self, entry):
        """Create or update one memory entry."""
        ...

    def get(self, key, scope=None):
        """Return one entry by key and optional scope."""
        ...

    def delete(self, key, scope=None):
        """Delete matching entries and return the deleted entries."""
        ...

    def list(self, scope=None, category=None):
        """List entries with optional filters."""
        ...

    def health(self):
        """Return provider health."""
        ...


class JsonMemoryStorage:
    """JSON file-backed Memory storage provider."""

    provider_name = "json"

    def __init__(self, path=None):
        """Create JSON storage at a project-local path by default."""
        self.path = Path(path or Path("memory") / "memory.json")

    def upsert(self, entry):
        """Create or update one memory entry."""
        entries = self.list()
        replaced = False
        updated_entries = []

        for existing in entries:
            if existing.key == entry.key and existing.scope == entry.scope:
                updated_entries.append(entry)
                replaced = True
            else:
                updated_entries.append(existing)

        if not replaced:
            updated_entries.append(entry)

        self.write_entries(updated_entries)
        trace_event(
            "memory.store",
            action="upsert",
            key=entry.key,
            scope=entry.scope,
            category=entry.category,
            storage=self.provider_name,
        )
        return entry

    def get(self, key, scope=None):
        """Return one entry by key and optional scope."""
        normalized_key = str(key).strip()
        candidates = [
            entry
            for entry in self.list()
            if entry.key == normalized_key and (scope is None or entry.scope == scope)
        ]

        if len(candidates) == 0:
            return None

        return sorted(candidates, key=lambda entry: entry.updated_at, reverse=True)[0]

    def delete(self, key, scope=None):
        """Delete matching entries and return the deleted entries."""
        normalized_key = str(key).strip()
        kept = []
        deleted = []

        for entry in self.list():
            if entry.key == normalized_key and (scope is None or entry.scope == scope):
                deleted.append(entry)
            else:
                kept.append(entry)

        self.write_entries(kept)
        trace_event(
            "memory.store",
            action="delete",
            key=normalized_key,
            scope=scope or "any",
            deleted=len(deleted),
            storage=self.provider_name,
        )
        return deleted

    def list(self, scope=None, category=None):
        """List entries with optional filters."""
        entries = self.read_entries()

        if scope is not None:
            entries = [entry for entry in entries if entry.scope == scope]

        if category is not None:
            entries = [entry for entry in entries if entry.category == category]

        return sorted(entries, key=lambda entry: (entry.category, entry.key, entry.scope))

    def read_entries(self):
        """Read all entries from disk."""
        if not self.path.exists():
            trace_event("memory.storage", provider=self.provider_name, path=str(self.path), entries=0)
            return []

        with self.path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        entries = [memory_entry_from_dict(item) for item in payload.get("entries", [])]
        trace_event("memory.storage", provider=self.provider_name, path=str(self.path), entries=len(entries))
        return entries

    def write_entries(self, entries):
        """Write all entries to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"entries": [entry.to_dict() for entry in entries]}

        with self.path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)

    def health(self):
        """Return JSON storage health."""
        return AbilityHealth(
            status="ok",
            provider=self.provider_name,
            message=f"Memory storage path: {self.path}",
        )


class InMemoryStorage:
    """In-memory storage provider for tests and session memories."""

    provider_name = "memory"

    def __init__(self, entries=None):
        """Create an in-memory storage provider."""
        self.entries = list(entries or [])

    def upsert(self, entry):
        """Create or update one entry."""
        self.entries = [
            existing
            for existing in self.entries
            if not (existing.key == entry.key and existing.scope == entry.scope)
        ]
        self.entries.append(entry)
        return entry

    def get(self, key, scope=None):
        """Return one entry by key."""
        candidates = [
            entry
            for entry in self.entries
            if entry.key == key and (scope is None or entry.scope == scope)
        ]
        return candidates[-1] if candidates else None

    def delete(self, key, scope=None):
        """Delete matching entries."""
        deleted = [
            entry
            for entry in self.entries
            if entry.key == key and (scope is None or entry.scope == scope)
        ]
        self.entries = [
            entry
            for entry in self.entries
            if not (entry.key == key and (scope is None or entry.scope == scope))
        ]
        return deleted

    def list(self, scope=None, category=None):
        """List stored entries."""
        entries = list(self.entries)

        if scope is not None:
            entries = [entry for entry in entries if entry.scope == scope]

        if category is not None:
            entries = [entry for entry in entries if entry.category == category]

        return entries

    def health(self):
        """Return in-memory storage health."""
        return AbilityHealth(status="ok", provider=self.provider_name, message="In-memory storage is active.")
