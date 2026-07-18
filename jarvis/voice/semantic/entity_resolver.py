"""Resolver registry and entity resolvers for semantic transcripts."""

from dataclasses import dataclass, field, replace
from time import perf_counter

from jarvis.voice.semantic.graph import EDGE_COMPANY, EntityNode
from jarvis.voice.semantic.models import ResolvedEntity, ResolverTrace, SemanticCorrection


ENTITY_SOURCE_KNOWN_PERSON = "known_person"
ENTITY_SOURCE_KNOWN_PLACE = "known_place"
ENTITY_SOURCE_MEMORY = "memory"
ENTITY_SOURCE_CONTACTS = "contacts"
ENTITY_SOURCE_CALENDAR = "calendar"
ENTITY_SOURCE_USER_VOCAB = "user_vocab"
ENTITY_SOURCE_SEMANTIC_RULE = "semantic_rule"
ENTITY_SOURCE_ENTITY_GRAPH = "entity_graph"

RESOLVER_PRIORITY_WEIGHTS = {
    ENTITY_SOURCE_CONTACTS: 1.0,
    ENTITY_SOURCE_MEMORY: 0.9,
    ENTITY_SOURCE_CALENDAR: 0.82,
    ENTITY_SOURCE_ENTITY_GRAPH: 0.78,
    ENTITY_SOURCE_KNOWN_PERSON: 0.72,
    ENTITY_SOURCE_KNOWN_PLACE: 0.72,
    ENTITY_SOURCE_USER_VOCAB: 0.68,
    ENTITY_SOURCE_SEMANTIC_RULE: 0.55,
}


@dataclass(frozen=True)
class KnownEntity:
    """A known person, place, or other entity."""

    type: str
    value: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    id: str = ""
    source: str = ENTITY_SOURCE_SEMANTIC_RULE
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ResolverResult:
    """Result from one semantic resolver."""

    resolver: str
    entities: tuple[ResolvedEntity, ...] = field(default_factory=tuple)
    corrections: tuple[SemanticCorrection, ...] = field(default_factory=tuple)


class BaseEntityResolver:
    """Base resolver plugin."""

    name = "base"
    priority = 100
    source = ENTITY_SOURCE_SEMANTIC_RULE

    def resolve(self, text, context, preferred_types=()):
        """Return entities and corrections for text."""
        return ResolverResult(resolver=self.name)


class KnownEntityResolver(BaseEntityResolver):
    """Resolve one group of known entities."""

    entity_type = ""
    source = ENTITY_SOURCE_SEMANTIC_RULE

    def __init__(self, entities=()):
        """Create a resolver for known entities."""
        self.entities = tuple(entities or ())

    def resolve(self, text, context, preferred_types=()):
        """Resolve matching aliases and candidate corrections."""
        transcript = str(text or "")
        preferred_types = tuple(preferred_types or ())
        entities = []
        corrections = []

        for entity in self.entities:
            matched_alias = ""

            for alias in entity.aliases:
                if alias and alias in transcript:
                    matched_alias = alias
                    entities.append(to_resolved_entity(entity, alias, self.name))
                    break

            if not matched_alias:
                continue

            if matched_alias == entity.value:
                continue

            confidence = confidence_for_entity(entity, preferred_types)
            corrections.append(
                SemanticCorrection(
                    source=matched_alias,
                    target=entity.value,
                    reason=f"{entity.source}_match",
                    confidence=confidence,
                    entity_source=entity.source,
                    resolver=self.name,
                )
            )

        return ResolverResult(
            resolver=self.name,
            entities=tuple(dedupe_resolved_entities(entities)),
            corrections=tuple(dedupe_corrections(corrections)),
        )


class KnownPeopleResolver(KnownEntityResolver):
    """Resolve known people."""

    name = "KnownPeopleResolver"
    priority = 40
    entity_type = "person"
    source = ENTITY_SOURCE_KNOWN_PERSON


class KnownPlaceResolver(KnownEntityResolver):
    """Resolve known places."""

    name = "KnownPlaceResolver"
    priority = 50
    entity_type = "place"
    source = ENTITY_SOURCE_KNOWN_PLACE


class MemoryEntityResolver(KnownEntityResolver):
    """Placeholder resolver for future Memory-backed entities."""

    name = "MemoryEntityResolver"
    priority = 20
    source = ENTITY_SOURCE_MEMORY


class ContactEntityResolver(KnownEntityResolver):
    """Placeholder resolver for future Contacts-backed entities."""

    name = "ContactEntityResolver"
    priority = 10
    source = ENTITY_SOURCE_CONTACTS

    def __init__(self, entities=(), repository=None):
        """Create a contact resolver from repository-backed contacts."""
        super().__init__(entities)
        self.repository = repository

    def resolve(self, text, context, preferred_types=()):
        """Resolve contacts by display name or alias."""
        if self.repository is None:
            return super().resolve(text, context, preferred_types)

        contacts = []
        for contact in self.repository.list():
            contacts.append(
                KnownEntity(
                    type="person",
                    value=contact.display_name,
                    aliases=tuple(dict.fromkeys((contact.display_name, *contact.aliases))),
                    id=contact.id,
                    source=ENTITY_SOURCE_CONTACTS,
                    confidence=float(getattr(contact, "confidence", 1.0)),
                    metadata={"contact": contact},
                )
            )

        result = KnownEntityResolver(contacts).resolve(text, context, preferred_types)
        entities = tuple(replace(entity, resolver=self.name) for entity in result.entities)
        corrections = tuple(replace(correction, resolver=self.name) for correction in result.corrections)
        return ResolverResult(resolver=self.name, entities=entities, corrections=corrections)


class CalendarHistoryResolver(KnownEntityResolver):
    """Placeholder resolver for future Calendar-history entities."""

    name = "CalendarHistoryResolver"
    priority = 30
    source = ENTITY_SOURCE_CALENDAR


class CrossResolver(BaseEntityResolver):
    """Resolve one-hop graph relationships such as '아야 회사'."""

    name = "CrossResolver"
    priority = 60
    source = ENTITY_SOURCE_ENTITY_GRAPH

    def resolve(self, text, context, preferred_types=()):
        """Resolve shallow entity graph relationships."""
        graph = getattr(context, "entity_graph", None)

        if graph is None or int(getattr(context, "max_resolver_depth", 2) or 0) < 2:
            return ResolverResult(resolver=self.name)

        transcript = str(text or "")
        entities = []

        for node in graph.nodes.values():
            if node.type != "person":
                continue

            aliases = tuple(dict.fromkeys((node.name, *node.aliases)))

            if not any(alias and alias in transcript for alias in aliases):
                continue

            if "회사" not in transcript:
                continue

            for edge in graph.find_edges(source_id=node.id, edge_type=EDGE_COMPANY):
                if edge.target_id:
                    target = graph.get_node(edge.target_id)
                    if target is not None:
                        entities.append(
                            ResolvedEntity(
                                id=target.id,
                                type=target.type,
                                value=target.name,
                                source_text="회사",
                                confidence=edge.confidence,
                                source=ENTITY_SOURCE_ENTITY_GRAPH,
                                resolver=self.name,
                            )
                        )
                elif edge.value:
                    entities.append(
                        ResolvedEntity(
                            id=entity_id("concept", str(edge.value)),
                            type="concept",
                            value=str(edge.value),
                            source_text="회사",
                            confidence=edge.confidence,
                            source=ENTITY_SOURCE_ENTITY_GRAPH,
                            resolver=self.name,
                        )
                    )

        return ResolverResult(resolver=self.name, entities=tuple(dedupe_resolved_entities(entities)))


class ResolverRegistry:
    """Run semantic resolver plugins in priority order."""

    version = "resolver-registry-v1"

    def __init__(self, resolvers=None):
        """Create a resolver registry."""
        self.resolvers = tuple(sorted(resolvers or (), key=lambda resolver: resolver.priority))

    def with_context(self, context):
        """Return a registry enriched with context entities."""
        people = list(default_people())
        places = list(default_places())

        for person in getattr(context, "known_people", ()) or ():
            people.append(
                KnownEntity(
                    type="person",
                    value=person,
                    aliases=(person,),
                    id=entity_id("person", person),
                    source=ENTITY_SOURCE_KNOWN_PERSON,
                )
            )

        for place in getattr(context, "known_places", ()) or ():
            places.append(
                KnownEntity(
                    type="place",
                    value=place,
                    aliases=(place,),
                    id=entity_id("place", place),
                    source=ENTITY_SOURCE_KNOWN_PLACE,
                )
            )

        contact_repository = getattr(context, "contact_repository", None)
        contact_entities = []
        if contact_repository is not None:
            for contact in contact_repository.list():
                contact_entities.append(
                    KnownEntity(
                        type="person",
                        value=contact.display_name,
                        aliases=tuple(dict.fromkeys((contact.display_name, *contact.aliases))),
                        id=contact.id,
                        source=ENTITY_SOURCE_CONTACTS,
                        confidence=float(getattr(contact, "confidence", 1.0)),
                    )
                )

        resolvers = (
            ContactEntityResolver(dedupe_entities(contact_entities), repository=None),
            MemoryEntityResolver(),
            CalendarHistoryResolver(),
            KnownPeopleResolver(dedupe_entities(people)),
            KnownPlaceResolver(dedupe_entities(places)),
            CrossResolver(),
        )
        graph = getattr(context, "entity_graph", None)
        if graph is not None:
            for entity in (*dedupe_entities(contact_entities), *dedupe_entities(people), *dedupe_entities(places)):
                graph.add_node(to_entity_node(entity))
        return ResolverRegistry(resolvers)

    def run(self, text, context, preferred_types=()):
        """Run all resolvers and return entities, corrections, and traces."""
        all_entities = []
        all_corrections = []
        traces = []

        for resolver in self.resolvers:
            started = perf_counter()
            result = resolver.resolve(text, context, preferred_types)
            latency_ms = int((perf_counter() - started) * 1000)
            all_entities.extend(result.entities)
            all_corrections.extend(result.corrections)
            status = "matched" if result.entities or result.corrections else "miss"
            traces.append(
                ResolverTrace(
                    resolver=resolver.name,
                    status=status,
                    latency_ms=latency_ms,
                    entities=result.entities,
                    corrections=result.corrections,
                )
            )

        return (
            tuple(merge_resolved_entities(all_entities)),
            tuple(dedupe_corrections(all_corrections)),
            tuple(traces),
        )

    def resolve_all(self, text):
        """Compatibility helper returning entities present in text."""
        entities, _, _ = self.run(text, context=None, preferred_types=())
        return entities

    def correction_for(self, text, entity_type="", preferred_types=()):
        """Compatibility helper returning the best correction."""
        _, corrections, _ = self.run(text, context=None, preferred_types=preferred_types)
        if entity_type:
            corrections = tuple(
                correction for correction in corrections if correction.reason.startswith(f"known_{entity_type}")
            )
        return best_correction(corrections)


class EntityRegistry(ResolverRegistry):
    """Backward-compatible semantic registry name."""

    def __init__(self, entities=None, resolvers=None):
        """Create a registry from known entities or resolver plugins."""
        if resolvers is not None:
            super().__init__(resolvers)
            return

        entities = tuple(entities or default_entities())
        people = [entity for entity in entities if entity.type == "person"]
        places = [entity for entity in entities if entity.type == "place"]
        super().__init__(
            (
                KnownPeopleResolver(people),
                KnownPlaceResolver(places),
            )
        )


def default_entities():
    """Return Jarvis' initial local known entities."""
    return (*default_people(), *default_places())


def default_people():
    """Return built-in known people."""
    return (
        KnownEntity(
            "person",
            "아야",
            ("아야", "아이", "하야", "하얀", "아연", "아연와", "아야한테", "아야에게"),
            id="person_aya",
            source=ENTITY_SOURCE_KNOWN_PERSON,
        ),
        KnownEntity("person", "유이", ("유이", "유이랑"), id="person_yui", source=ENTITY_SOURCE_KNOWN_PERSON),
        KnownEntity("person", "유리", ("유리", "유리랑"), id="person_yuri", source=ENTITY_SOURCE_KNOWN_PERSON),
    )


def default_places():
    """Return built-in known places."""
    return (
        KnownEntity("place", "서울역", ("서울역", "설립", "서울력"), id="place_seoul_station", source=ENTITY_SOURCE_KNOWN_PLACE),
        KnownEntity("place", "롯데월드", ("롯데월드",), id="place_lotte_world", source=ENTITY_SOURCE_KNOWN_PLACE),
        KnownEntity(
            "place",
            "강릉 고용보험공단",
            ("강릉 고용보험공단",),
            id="place_gangneung_employment_center",
            source=ENTITY_SOURCE_KNOWN_PLACE,
        ),
    )


def to_resolved_entity(entity, alias, resolver):
    """Convert a known entity to a resolved entity."""
    score = final_score(entity.source, entity.confidence, context_match=1.0)
    return ResolvedEntity(
        id=entity.id or entity_id(entity.type, entity.value),
        type=entity.type,
        value=entity.value,
        source_text=alias,
        confidence=round(score, 3),
        source=entity.source,
        resolver=resolver,
    )


def to_entity_node(entity):
    """Convert a known entity into a graph node."""
    return EntityNode(
        id=entity.id or entity_id(entity.type, entity.value),
        type=entity.type,
        name=entity.value,
        aliases=entity.aliases,
        sources=(entity.source,),
        confidence_by_source={entity.source: entity.confidence},
    )


def confidence_for_entity(entity, preferred_types):
    """Return a simple confidence score for an entity correction."""
    context_match = 1.0

    if preferred_types and entity.type in preferred_types:
        context_match = 1.0
        base = 0.96 if entity.type == "place" else 0.94
    else:
        context_match = 0.86
        base = 0.91 if entity.type == "person" else 0.9

    return round(final_score(entity.source, base, context_match=context_match), 3)


def final_score(source, confidence, source_freshness=1.0, context_match=1.0):
    """Combine priority, confidence, freshness, and context fit."""
    priority_weight = RESOLVER_PRIORITY_WEIGHTS.get(source, 0.5)
    score = (priority_weight * 0.25) + (confidence * 0.45) + (source_freshness * 0.1) + (context_match * 0.2)
    return min(1.0, max(0.0, score))


def best_correction(corrections):
    """Return the highest-confidence non-ambiguous correction."""
    corrections = tuple(corrections or ())

    if not corrections:
        return None

    max_confidence = max(correction.confidence for correction in corrections)
    best = [correction for correction in corrections if correction.confidence == max_confidence]

    if len(best) != 1:
        return None

    return best[0]


def dedupe_entities(entities):
    """Remove duplicate entity aliases while preserving order."""
    seen = set()
    deduped = []

    for entity in entities:
        key = (entity.type, entity.value, entity.aliases, entity.source)

        if key in seen:
            continue

        seen.add(key)
        deduped.append(entity)

    return tuple(deduped)


def dedupe_resolved_entities(entities):
    """Remove duplicate resolved entities while preserving order."""
    seen = set()
    deduped = []

    for entity in entities:
        key = (entity.type, entity.value, entity.source)

        if key in seen:
            continue

        seen.add(key)
        deduped.append(entity)

    return tuple(deduped)


def merge_resolved_entities(entities):
    """Merge duplicate entities by canonical ID, keeping provenance."""
    merged = {}
    order = []

    for entity in entities:
        key = entity.id or entity_id(entity.type, entity.value)

        if key not in merged:
            merged[key] = entity
            order.append(key)
            continue

        existing = merged[key]

        if entity.confidence > existing.confidence:
            merged[key] = replace(
                entity,
                source_text=existing.source_text or entity.source_text,
                source=merge_csv(existing.source, entity.source),
            )
        else:
            merged[key] = replace(
                existing,
                source=merge_csv(existing.source, entity.source),
                confidence=max(existing.confidence, entity.confidence),
            )

    return tuple(merged[key] for key in order)


def merge_csv(*values):
    """Merge simple source strings without introducing a collection type."""
    parts = []
    for value in values:
        for part in str(value or "").split(","):
            part = part.strip()
            if part and part not in parts:
                parts.append(part)
    return ",".join(parts)


def dedupe_corrections(corrections):
    """Remove duplicate corrections while preserving order."""
    seen = set()
    deduped = []

    for correction in corrections:
        key = (correction.source, correction.target, correction.reason)

        if key in seen:
            continue

        seen.add(key)
        deduped.append(correction)

    return tuple(deduped)


def entity_id(entity_type, value):
    """Return a stable simple entity ID."""
    slugs = {
        "아야": "aya",
        "유이": "yui",
        "유리": "yuri",
        "아이": "ai",
        "서울역": "seoul_station",
        "롯데월드": "lotte_world",
        "강릉 고용보험공단": "gangneung_employment_center",
    }
    slug = slugs.get(value, str(value or "").strip().replace(" ", "_").lower())
    return f"{entity_type}_{slug}"
