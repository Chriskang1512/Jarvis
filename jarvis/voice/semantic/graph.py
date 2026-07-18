"""In-memory entity graph foundation for semantic intelligence."""

from dataclasses import dataclass, field, replace
from datetime import datetime


NODE_PERSON = "person"
NODE_PLACE = "place"
NODE_ORGANIZATION = "organization"
NODE_DATE = "date"
NODE_CONCEPT = "concept"
NODE_EMAIL = "email"
NODE_PHONE = "phone"

EDGE_RELATIONSHIP = "RELATIONSHIP"
EDGE_JOB = "JOB"
EDGE_COUNTRY = "COUNTRY"
EDGE_BIRTHDAY = "BIRTHDAY"
EDGE_COMPANY = "COMPANY"
EDGE_LOCATION = "LOCATION"
EDGE_ALIAS = "ALIAS"
EDGE_EMAIL = "EMAIL"
EDGE_PHONE = "PHONE"
EDGE_TAG = "TAG"
EDGE_LANGUAGE = "LANGUAGE"
EDGE_TIMEZONE = "TIMEZONE"
EDGE_WORKS_AT = "WORKS_AT"


@dataclass(frozen=True)
class EntityNode:
    """One entity node in Jarvis' semantic graph."""

    id: str
    type: str
    name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    sources: tuple[str, ...] = field(default_factory=tuple)
    confidence_by_source: dict = field(default_factory=dict)
    revision: int = 0
    source: str = ""
    verified: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self):
        """Return a serializable representation."""
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "aliases": list(self.aliases),
            "sources": list(self.sources),
            "confidence_by_source": dict(self.confidence_by_source),
            "revision": self.revision,
            "source": self.source,
            "verified": self.verified,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class EntityEdge:
    """One relationship edge in Jarvis' semantic graph."""

    source_id: str
    type: str
    target_id: str = ""
    value: object = None
    source: str = ""
    confidence: float = 1.0
    revision: int = 0
    verified: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self):
        """Return a serializable representation."""
        return {
            "source_id": self.source_id,
            "type": self.type,
            "target_id": self.target_id,
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
            "revision": self.revision,
            "verified": self.verified,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class EntityGraph:
    """Small in-memory graph with merge and provenance support."""

    def __init__(self):
        """Create an empty graph."""
        self.nodes = {}
        self.edges = []

    def add_node(self, node):
        """Add or merge one node."""
        now = current_timestamp()
        incoming = ensure_node_timestamps(node, now)
        existing = self.nodes.get(incoming.id)

        if existing is None:
            self.nodes[incoming.id] = incoming
            return incoming

        merged = merge_nodes(existing, incoming, now)
        self.nodes[merged.id] = merged
        return merged

    def get_node(self, node_id):
        """Return one node by ID."""
        return self.nodes.get(node_id)

    def remove_node(self, node_id):
        """Remove one node and attached edges."""
        if node_id not in self.nodes:
            return False

        del self.nodes[node_id]
        self.edges = [
            edge for edge in self.edges if edge.source_id != node_id and edge.target_id != node_id
        ]
        return True

    def add_edge(self, edge):
        """Add or replace one edge."""
        now = current_timestamp()
        incoming = ensure_edge_timestamps(edge, now)

        for index, existing in enumerate(self.edges):
            if same_edge(existing, incoming):
                merged = replace(
                    existing,
                    value=incoming.value,
                    source=incoming.source or existing.source,
                    confidence=incoming.confidence,
                    revision=incoming.revision or existing.revision,
                    verified=incoming.verified or existing.verified,
                    updated_at=now,
                )
                self.edges[index] = merged
                return merged

        self.edges.append(incoming)
        return incoming

    def remove_edge(self, source_id, edge_type, target_id="", value=None):
        """Remove matching edges."""
        before = len(self.edges)
        self.edges = [
            edge
            for edge in self.edges
            if not (
                edge.source_id == source_id
                and edge.type == edge_type
                and (target_id == "" or edge.target_id == target_id)
                and (value is None or edge.value == value)
            )
        ]
        return before != len(self.edges)

    def find_edges(self, source_id="", edge_type="", target_id=""):
        """Find edges by optional source, type, and target."""
        return [
            edge
            for edge in self.edges
            if (not source_id or edge.source_id == source_id)
            and (not edge_type or edge.type == edge_type)
            and (not target_id or edge.target_id == target_id)
        ]

    def neighbors(self, node_id, edge_type=""):
        """Return neighbor nodes or primitive values from outgoing edges."""
        neighbors = []

        for edge in self.find_edges(source_id=node_id, edge_type=edge_type):
            if edge.target_id:
                neighbors.append(self.get_node(edge.target_id))
            else:
                neighbors.append(edge.value)

        return [neighbor for neighbor in neighbors if neighbor is not None]


def merge_nodes(existing, incoming, now):
    """Merge two canonical nodes."""
    aliases = tuple(dict.fromkeys((*existing.aliases, *incoming.aliases, existing.name, incoming.name)))
    sources = tuple(dict.fromkeys((*existing.sources, *incoming.sources)))
    confidence_by_source = dict(existing.confidence_by_source)
    confidence_by_source.update(incoming.confidence_by_source)
    return replace(
        existing,
        name=existing.name or incoming.name,
        aliases=aliases,
        sources=sources,
        confidence_by_source=confidence_by_source,
        revision=max(existing.revision, incoming.revision),
        source=incoming.source or existing.source,
        verified=existing.verified or incoming.verified,
        updated_at=now,
    )


def same_edge(left, right):
    """Return whether two edges represent the same fact."""
    return (
        left.source_id == right.source_id
        and left.type == right.type
        and left.target_id == right.target_id
        and left.value == right.value
    )


def ensure_node_timestamps(node, now):
    """Fill node timestamps."""
    return replace(node, created_at=node.created_at or now, updated_at=node.updated_at or now)


def ensure_edge_timestamps(edge, now):
    """Fill edge timestamps."""
    return replace(edge, created_at=edge.created_at or now, updated_at=edge.updated_at or now)


def current_timestamp():
    """Return a stable ISO timestamp."""
    return datetime.now().isoformat(timespec="seconds")
