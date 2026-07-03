from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class MemoryCategory(str, Enum):
    """Structured long-term memory categories."""

    PREFERENCE = "preference"
    FACT = "fact"
    GOAL = "goal"
    PROJECT = "project"
    ROUTINE = "routine"


def current_timestamp():
    """Return a stable timestamp string for memory metadata."""
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class MemoryRecord:
    """Represent one long-term memory item."""

    content: str
    title: str = ""
    category: MemoryCategory = MemoryCategory.FACT
    source: str = "manual"
    tags: list = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=current_timestamp)
    updated_at: str = field(default_factory=current_timestamp)

    def to_dict(self):
        """Return a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "category": self.category.value,
            "source": self.source,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def memory_from_dict(data):
    """Create a MemoryRecord from stored data."""
    return MemoryRecord(
        id=data.get("id", str(uuid4())),
        title=data.get("title", ""),
        content=data.get("content", ""),
        category=normalize_category(data.get("category", MemoryCategory.FACT.value)),
        source=data.get("source", "manual"),
        tags=list(data.get("tags", [])),
        created_at=data.get("created_at", current_timestamp()),
        updated_at=data.get("updated_at", current_timestamp()),
    )


def normalize_category(category):
    """Return a MemoryCategory from string or enum input."""
    if isinstance(category, MemoryCategory):
        return category

    return MemoryCategory(str(category).lower())
