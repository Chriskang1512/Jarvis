import json
from pathlib import Path

from jarvis.memory_store.models import MemoryRecord, current_timestamp, memory_from_dict, normalize_category


class InMemoryStore:
    """In-memory long-term memory store used by tests and early runtime."""

    def __init__(self):
        """Create an empty memory store."""
        self.memories = {}

    def load(self):
        """Load memories from backend."""
        return self.list()

    def save(self):
        """Persist memories to backend."""
        return None

    def create(self, memory):
        """Create one memory."""
        self.memories[memory.id] = memory
        self.save()
        return memory

    def get(self, memory_id):
        """Return one memory by ID."""
        return self.memories.get(memory_id)

    def update(self, memory_id, content=None, title=None, category=None, source=None, tags=None):
        """Update one memory and return it."""
        memory = self.get(memory_id)

        if memory is None:
            return None

        if content is not None:
            memory.content = content

        if title is not None:
            memory.title = title

        if category is not None:
            memory.category = normalize_category(category)

        if source is not None:
            memory.source = source

        if tags is not None:
            memory.tags = list(tags)

        memory.updated_at = current_timestamp()
        self.save()
        return memory

    def delete(self, memory_id):
        """Delete one memory by ID."""
        if memory_id not in self.memories:
            return False

        del self.memories[memory_id]
        self.save()
        return True

    def list(self):
        """Return all memories sorted by creation time."""
        return sorted(self.memories.values(), key=lambda memory: memory.created_at)

    def find_by_category(self, category):
        """Return memories in one category."""
        normalized_category = normalize_category(category)
        return [memory for memory in self.list() if memory.category == normalized_category]

    def find_by_tag(self, tag):
        """Return memories with one tag."""
        return [memory for memory in self.list() if tag in memory.tags]

    def find_recent(self, limit=5):
        """Return the most recent memories."""
        return list(reversed(self.list()))[:limit]

    def search(self, query):
        """Return memories containing a simple case-insensitive query."""
        normalized_query = query.lower()
        return [
            memory
            for memory in self.list()
            if normalized_query in memory.content.lower() or normalized_query in memory.title.lower()
        ]


class JsonMemoryStore(InMemoryStore):
    """JSON-backed long-term memory store."""

    def __init__(self, path):
        """Create a JSON memory store at one file path."""
        super().__init__()
        self.path = Path(path)

    def load(self):
        """Load memories from a JSON file."""
        if not self.path.exists():
            self.memories = {}
            return []

        with self.path.open("r", encoding="utf-8") as file:
            raw_memories = json.load(file)

        self.memories = {
            memory.id: memory
            for memory in [memory_from_dict(data) for data in raw_memories]
        }
        return self.list()

    def save(self):
        """Persist memories to a JSON file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self.path.open("w", encoding="utf-8") as file:
            json.dump([memory.to_dict() for memory in self.list()], file, indent=2, ensure_ascii=False)
