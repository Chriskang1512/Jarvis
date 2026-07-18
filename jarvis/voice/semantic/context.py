"""Context passed into semantic transcript normalization."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SemanticTranscriptContext:
    """Conversation and entity context for STT transcript repair."""

    conversation_state: str = ""
    pending_field: str = ""
    last_question: str = ""
    last_intent: str = ""
    last_task_id: str = ""
    last_calendar_event: object = None
    known_people: tuple[str, ...] = field(default_factory=tuple)
    known_places: tuple[str, ...] = field(default_factory=tuple)
    recent_entities: tuple[str, ...] = field(default_factory=tuple)
    known_entities_version: str = "local-v1"
    entity_graph: object = None
    contact_repository: object = None
    max_resolver_depth: int = 2
