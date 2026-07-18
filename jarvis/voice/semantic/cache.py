"""Small TTL cache for semantic resolver results."""

from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class SemanticCacheEntry:
    """Cached resolver output."""

    value: object
    created_at: float


class SemanticEntityCache:
    """Bounded TTL cache for resolver results."""

    def __init__(self, ttl_seconds=300, max_size=256):
        """Create an entity cache."""
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.entries = OrderedDict()
        self.hit_count = 0
        self.miss_count = 0
        self.invalidations = 0

    def get(self, key):
        """Return a cached value or None."""
        entry = self.entries.get(key)

        if entry is None:
            self.miss_count += 1
            return None

        if self.is_expired(entry):
            self.entries.pop(key, None)
            self.miss_count += 1
            return None

        self.entries.move_to_end(key)
        self.hit_count += 1
        return entry.value

    def set(self, key, value):
        """Store a cached value."""
        self.entries[key] = SemanticCacheEntry(value=value, created_at=monotonic())
        self.entries.move_to_end(key)
        self.trim()

    def invalidate(self):
        """Clear the cache."""
        self.entries.clear()
        self.invalidations += 1

    def is_expired(self, entry):
        """Return whether a cache entry is expired."""
        return monotonic() - entry.created_at > self.ttl_seconds

    def trim(self):
        """Trim oldest entries."""
        while len(self.entries) > self.max_size:
            self.entries.popitem(last=False)

    def metrics(self):
        """Return cache metrics."""
        return {
            "cache_hit": self.hit_count,
            "cache_miss": self.miss_count,
            "cache_size": len(self.entries),
            "cache_invalidations": self.invalidations,
        }


def semantic_cache_key(text, context, registry_version):
    """Return a conservative cache key."""
    return (
        str(text or ""),
        str(getattr(context, "pending_field", "") or ""),
        str(getattr(context, "conversation_state", "") or ""),
        str(getattr(context, "known_entities_version", "") or ""),
        str(registry_version or ""),
    )
