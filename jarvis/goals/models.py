"""Domain models for goal-oriented semantic context."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any
from uuid import uuid4


class ProvenanceSource(IntEnum):
    """Context merge priority. Larger values win."""

    SYSTEM_DEFAULT = 10
    USER_PREFERENCE = 20
    CONVERSATION_CONTEXT = 30
    CURRENT_TURN_ENTITY = 40
    EXPLICIT_CONTROL_COMMAND = 50
    EXPLICIT_INPUT = 60


@dataclass(frozen=True)
class Provenance:
    source: ProvenanceSource
    detail: str = ""
    turn_id: str = ""
    parser_id: str = ""
    source_field: str = ""
    captured_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.name,
            "detail": self.detail,
            "turn_id": self.turn_id,
            "parser_id": self.parser_id,
            "source_field": self.source_field,
            "captured_at": self.captured_at,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Provenance":
        return cls(
            source=ProvenanceSource[str(value["source"])],
            detail=str(value.get("detail", "")),
            turn_id=str(value.get("turn_id", "")),
            parser_id=str(value.get("parser_id", "")),
            source_field=str(value.get("source_field", "")),
            captured_at=str(value.get("captured_at", "")),
            confidence=float(value.get("confidence", 1.0)),
        )


@dataclass(frozen=True)
class SemanticSlot:
    name: str
    value: Any
    value_type: str = "string"
    confidence: float = 1.0
    provenance: Provenance = field(
        default_factory=lambda: Provenance(ProvenanceSource.EXPLICIT_INPUT)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "value_type": self.value_type,
            "confidence": self.confidence,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SemanticSlot":
        return cls(
            name=str(value["name"]),
            value=value.get("value"),
            value_type=str(value.get("value_type", "string")),
            confidence=float(value.get("confidence", 1.0)),
            provenance=Provenance.from_dict(value["provenance"]),
        )


@dataclass(frozen=True)
class EntityReference:
    entity_type: str
    value: Any
    entity_id: str = ""
    mention: str = ""
    confidence: float = 1.0
    provenance: Provenance = field(
        default_factory=lambda: Provenance(ProvenanceSource.CURRENT_TURN_ENTITY)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "value": self.value,
            "entity_id": self.entity_id,
            "mention": self.mention,
            "confidence": self.confidence,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EntityReference":
        return cls(
            entity_type=str(value["entity_type"]),
            value=value.get("value"),
            entity_id=str(value.get("entity_id", "")),
            mention=str(value.get("mention", "")),
            confidence=float(value.get("confidence", 1.0)),
            provenance=Provenance.from_dict(value["provenance"]),
        )


@dataclass(frozen=True)
class TemporalContext:
    timezone: str = "Asia/Seoul"
    reference_date: str = ""
    date: str = ""
    time: str = ""
    duration: str = ""
    expression: str = ""


@dataclass(frozen=True)
class LanguageContext:
    language: str = "ko"
    locale: str = "ko-KR"
    original_language: str = "ko"


@dataclass(frozen=True)
class PreviousResultContext:
    result_id: str = ""
    result_type: str = ""
    value: Any = None
    artifact_refs: tuple[dict[str, Any], ...] = ()
    producer_goal_id: str = ""


@dataclass(frozen=True)
class ContextLifecycle:
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_referenced_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    scope: str = "conversation"
    expiration_policy: str = "turn_window"
    confidence_decay: float = 0.90
    turn_index: int = 0


@dataclass(frozen=True)
class SemanticContext:
    domain: str = "general"
    slots: dict[str, SemanticSlot] = field(default_factory=dict)
    entities: tuple[EntityReference, ...] = ()
    temporal: TemporalContext = field(default_factory=TemporalContext)
    language: LanguageContext = field(default_factory=LanguageContext)
    previous_result: PreviousResultContext | None = None
    confidence: float = 0.0
    lifecycle: ContextLifecycle = field(default_factory=ContextLifecycle)

    @classmethod
    def empty(cls) -> "SemanticContext":
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "slots": {key: slot.to_dict() for key, slot in sorted(self.slots.items())},
            "entities": [entity.to_dict() for entity in self.entities],
            "temporal": asdict(self.temporal),
            "language": asdict(self.language),
            "previous_result": asdict(self.previous_result) if self.previous_result else None,
            "confidence": self.confidence,
            "lifecycle": asdict(self.lifecycle),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SemanticContext":
        previous = value.get("previous_result")
        if previous:
            previous = dict(previous)
            previous["artifact_refs"] = tuple(previous.get("artifact_refs", ()))
        return cls(
            domain=str(value.get("domain", "general")),
            slots={
                key: SemanticSlot.from_dict(slot)
                for key, slot in dict(value.get("slots", {})).items()
            },
            entities=tuple(
                EntityReference.from_dict(entity) for entity in value.get("entities", ())
            ),
            temporal=TemporalContext(**dict(value.get("temporal", {}))),
            language=LanguageContext(**dict(value.get("language", {}))),
            previous_result=PreviousResultContext(**previous) if previous else None,
            confidence=float(value.get("confidence", 0.0)),
            lifecycle=ContextLifecycle(**dict(value.get("lifecycle", {}))),
        )


@dataclass(frozen=True)
class GoalConstraint:
    description: str
    kind: str = "user"


@dataclass(frozen=True)
class SuccessCriterion:
    description: str
    required: bool = True
    criterion_id: str = field(
        default_factory=lambda: f"SC-{uuid4()}"
    )


@dataclass(frozen=True)
class GoalSpecification:
    goal_id: str
    original_input: str
    objective: str
    constraints: tuple[GoalConstraint, ...] = ()
    success_criteria: tuple[SuccessCriterion, ...] = ()
    context: SemanticContext = field(default_factory=SemanticContext.empty)
    confidence: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "original_input": self.original_input,
            "objective": self.objective,
            "constraints": [asdict(item) for item in self.constraints],
            "success_criteria": [asdict(item) for item in self.success_criteria],
            "context": self.context.to_dict(),
            "confidence": self.confidence,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GoalSpecification":
        return cls(
            goal_id=str(value["goal_id"]),
            original_input=str(value["original_input"]),
            objective=str(value["objective"]),
            constraints=tuple(
                GoalConstraint(**item) for item in value.get("constraints", ())
            ),
            success_criteria=tuple(
                SuccessCriterion(**item) for item in value.get("success_criteria", ())
            ),
            context=SemanticContext.from_dict(value.get("context", {})),
            confidence=float(value.get("confidence", 0.0)),
            created_at=str(value["created_at"]),
        )
