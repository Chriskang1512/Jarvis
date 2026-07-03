from jarvis.memory_store.models import MemoryCategory, MemoryRecord, normalize_category
from jarvis.memory_store.store import InMemoryStore


class MemoryManager:
    """Coordinate long-term memory storage and retrieval."""

    def __init__(self, store=None, diagnostics_collector=None):
        """Create a manager around a swappable memory store."""
        self.store = store or InMemoryStore()
        self.diagnostics_collector = diagnostics_collector

    def load(self):
        """Load memories through the underlying store."""
        memories = self.store.load()
        self.log_event("memory.loaded")
        return memories

    def remember(self, content, category=MemoryCategory.FACT, source="manual", tags=None):
        """Create a memory when the content is worth storing."""
        if not self.should_store(content):
            return None

        memory = MemoryRecord(
            content=content.strip(),
            category=normalize_category(category),
            source=source,
            tags=normalize_tags(tags),
        )
        created_memory = self.store.create(memory)
        self.log_event("memory.created")
        return created_memory

    def update(self, memory_id, content=None, category=None, source=None, tags=None):
        """Update one stored memory."""
        memory = self.store.update(
            memory_id=memory_id,
            content=content,
            category=category,
            source=source,
            tags=normalize_tags(tags) if tags is not None else None,
        )

        if memory is not None:
            self.log_event("memory.updated")

        return memory

    def delete(self, memory_id):
        """Delete one stored memory."""
        deleted = self.store.delete(memory_id)

        if deleted:
            self.log_event("memory.deleted")

        return deleted

    def get(self, memory_id):
        """Return one memory by ID."""
        memory = self.store.get(memory_id)
        self.log_event("memory.retrieved")
        return memory

    def find_by_category(self, category):
        """Return memories by category."""
        memories = self.store.find_by_category(category)
        self.log_event("memory.retrieved")
        return memories

    def find_by_tag(self, tag):
        """Return memories by tag."""
        memories = self.store.find_by_tag(tag)
        self.log_event("memory.retrieved")
        return memories

    def find_recent(self, limit=5):
        """Return recent memories."""
        memories = self.store.find_recent(limit=limit)
        self.log_event("memory.retrieved")
        return memories

    def search(self, query):
        """Return memories matching a simple text query."""
        memories = self.store.search(query)
        self.log_event("memory.retrieved")
        return memories

    def should_store(self, content):
        """Return whether content should be stored."""
        return content is not None and content.strip() != ""

    def log_event(self, message):
        """Publish one memory diagnostics event."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.log_event(message)


def normalize_tags(tags):
    """Return a normalized tag list."""
    if tags is None:
        return []

    return [str(tag).strip() for tag in tags if str(tag).strip() != ""]
