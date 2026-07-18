"""Models for semantic STT transcript normalization."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SemanticCorrection:
    """A single semantic transcript correction."""

    source: str
    target: str
    reason: str
    confidence: float = 1.0
    entity_source: str = "semantic_rule"
    resolver: str = "semantic_rule"

    def to_dict(self):
        """Return a serializable representation."""
        return {
            "from": self.source,
            "to": self.target,
            "reason": self.reason,
            "confidence": self.confidence,
            "source": self.entity_source,
            "resolver": self.resolver,
        }


@dataclass(frozen=True)
class ResolvedEntity:
    """A known entity resolved from the transcript."""

    type: str
    value: str
    source_text: str = ""
    confidence: float = 1.0
    id: str = ""
    source: str = "semantic_rule"
    resolver: str = ""

    def to_dict(self):
        """Return a serializable representation."""
        return {
            "id": self.id,
            "type": self.type,
            "value": self.value,
            "source_text": self.source_text,
            "confidence": self.confidence,
            "source": self.source,
            "resolver": self.resolver,
        }


@dataclass(frozen=True)
class SemanticHistoryStep:
    """One step in semantic transcript interpretation."""

    stage: str
    text: str = ""
    resolver: str = ""
    entities: tuple[ResolvedEntity, ...] = field(default_factory=tuple)
    corrections: tuple[SemanticCorrection, ...] = field(default_factory=tuple)
    confidence: float = 1.0

    def to_dict(self):
        """Return a serializable representation."""
        return {
            "stage": self.stage,
            "text": self.text,
            "resolver": self.resolver,
            "entities": [entity.to_dict() for entity in self.entities],
            "corrections": [correction.to_dict() for correction in self.corrections],
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ResolverTrace:
    """Trace for one resolver pass."""

    resolver: str
    status: str
    latency_ms: int = 0
    entities: tuple[ResolvedEntity, ...] = field(default_factory=tuple)
    corrections: tuple[SemanticCorrection, ...] = field(default_factory=tuple)

    def to_dict(self):
        """Return a serializable representation."""
        return {
            "resolver": self.resolver,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "entities": [entity.to_dict() for entity in self.entities],
            "corrections": [correction.to_dict() for correction in self.corrections],
        }


@dataclass(frozen=True)
class SemanticTranscriptResult:
    """Result of semantic transcript normalization."""

    raw_text: str
    normalized_text: str
    semantic_text: str
    corrections: tuple[SemanticCorrection, ...] = field(default_factory=tuple)
    resolved_entities: tuple[ResolvedEntity, ...] = field(default_factory=tuple)
    confidence: float = 1.0
    requires_clarification: bool = False
    clarification_question: str = ""
    source: str = "semantic"
    history: tuple[SemanticHistoryStep, ...] = field(default_factory=tuple)
    resolver_traces: tuple[ResolverTrace, ...] = field(default_factory=tuple)

    def correction_dicts(self):
        """Return corrections in log-friendly form."""
        return [correction.to_dict() for correction in self.corrections]

    def entity_dicts(self):
        """Return resolved entities in log-friendly form."""
        return [entity.to_dict() for entity in self.resolved_entities]

    def history_dicts(self):
        """Return semantic history in log-friendly form."""
        return [step.to_dict() for step in self.history]

    def resolver_trace_dicts(self):
        """Return resolver traces in log-friendly form."""
        return [trace.to_dict() for trace in self.resolver_traces]
