"""Conversation context merge and reference resolution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from jarvis.goals.models import (
    EntityReference,
    ContextLifecycle,
    PreviousResultContext,
    Provenance,
    ProvenanceSource,
    SemanticContext,
    SemanticSlot,
)


@dataclass(frozen=True)
class ContextKey:
    """Isolation boundary for stored conversational state."""

    user_id: str
    conversation_id: str
    session_id: str


@dataclass(frozen=True)
class TurnContext:
    turn_id: str
    context: SemanticContext


class ConversationContextEngine:
    """Store and merge semantic context per conversation session."""

    def __init__(
        self,
        *,
        max_turns=12,
        confidence_decay=0.90,
        min_confidence=0.35,
        clock=None,
    ):
        self.max_turns = int(max_turns)
        self.confidence_decay = float(confidence_decay)
        self.min_confidence = float(min_confidence)
        if self.max_turns < 1:
            raise ValueError("max_turns must be at least 1.")
        if not 0.0 < self.confidence_decay <= 1.0:
            raise ValueError("confidence_decay must be greater than 0 and at most 1.")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1.")
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._contexts: dict[ContextKey, list[TurnContext]] = {}
        self._results: dict[ContextKey, PreviousResultContext] = {}

    def get(
        self,
        session_id: str,
        *,
        user_id: str = "local",
        conversation_id: str = "default",
    ) -> SemanticContext:
        turns = self._contexts.get(
            ContextKey(user_id, conversation_id, session_id), ()
        )
        return turns[-1].context if turns else SemanticContext.empty()

    def save(
        self,
        session_id: str,
        context: SemanticContext,
        *,
        user_id: str = "local",
        conversation_id: str = "default",
        turn_id: str = "",
    ) -> None:
        key = ContextKey(user_id, conversation_id, session_id)
        turns = self._contexts.setdefault(key, [])
        index = len(turns) + 1
        now = self.clock().isoformat()
        lifecycle = replace(
            context.lifecycle,
            created_at=context.lifecycle.created_at or now,
            last_referenced_at=now,
            turn_index=index,
        )
        turns.append(
            TurnContext(
                turn_id=turn_id or f"turn-{index}",
                context=replace(context, lifecycle=lifecycle),
            )
        )
        if self.max_turns > 0:
            del turns[:-self.max_turns]

    def record_result(
        self,
        session_id: str,
        result: Any,
        *,
        result_id: str = "",
        result_type: str = "",
        artifact_refs: tuple[Any, ...] = (),
        producer_goal_id: str = "",
        user_id: str = "local",
        conversation_id: str = "default",
    ) -> PreviousResultContext:
        serialized_refs = tuple(
            ref.to_dict() if hasattr(ref, "to_dict") else dict(ref)
            for ref in artifact_refs
        )
        value = PreviousResultContext(
            result_id=result_id,
            result_type=result_type,
            value=result,
            artifact_refs=serialized_refs,
            producer_goal_id=producer_goal_id,
        )
        self._results[
            ContextKey(user_id, conversation_id, session_id)
        ] = value
        return value

    def merge(
        self,
        session_id: str,
        current: SemanticContext,
        *,
        explicit_input: dict[str, Any] | None = None,
        explicit_control: dict[str, Any] | None = None,
        user_preferences: dict[str, Any] | None = None,
        system_defaults: dict[str, Any] | None = None,
        references_previous_result: bool = False,
        user_id: str = "local",
        conversation_id: str = "default",
        turn_id: str = "",
    ) -> SemanticContext:
        """Merge sources using the documented strict precedence."""
        candidates: list[SemanticSlot] = []
        candidates.extend(
            self._make_slots(
                system_defaults, ProvenanceSource.SYSTEM_DEFAULT, turn_id=turn_id
            )
        )
        candidates.extend(
            self._make_slots(
                user_preferences, ProvenanceSource.USER_PREFERENCE, turn_id=turn_id
            )
        )

        prior = self.get(
            session_id, user_id=user_id, conversation_id=conversation_id
        )
        candidates.extend(
            replace(
                slot,
                confidence=slot.confidence * self.confidence_decay,
                provenance=replace(
                    slot.provenance,
                    source=ProvenanceSource.CONVERSATION_CONTEXT,
                    confidence=slot.provenance.confidence
                    * self.confidence_decay,
                ),
            )
            for slot in prior.slots.values()
            if slot.confidence * self.confidence_decay >= self.min_confidence
        )
        candidates.extend(current.slots.values())
        candidates.extend(
            self._make_slots(
                explicit_control,
                ProvenanceSource.EXPLICIT_CONTROL_COMMAND,
                turn_id=turn_id,
            )
        )
        candidates.extend(
            self._make_slots(
                explicit_input,
                ProvenanceSource.EXPLICIT_INPUT,
                turn_id=turn_id,
                parser_id="semantic_extractor",
            )
        )

        merged_slots: dict[str, SemanticSlot] = {}
        for slot in candidates:
            old = merged_slots.get(slot.name)
            if old is None or slot.provenance.source >= old.provenance.source:
                merged_slots[slot.name] = slot

        entities = self._merge_entities(
            prior.entities,
            current.entities,
            self.confidence_decay,
            self.min_confidence,
        )
        key = ContextKey(user_id, conversation_id, session_id)
        previous_result = (
            self._results.get(key) if references_previous_result else current.previous_result
        )
        confidence_values = [slot.confidence for slot in merged_slots.values()]
        confidence_values.extend(entity.confidence for entity in entities)
        confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else current.confidence
        )
        merged = replace(
            current,
            domain=current.domain if current.domain != "general" else prior.domain,
            slots=merged_slots,
            entities=entities,
            previous_result=previous_result,
            confidence=confidence,
            lifecycle=ContextLifecycle(
                created_at=prior.lifecycle.created_at
                if prior.lifecycle.turn_index
                else self.clock().isoformat(),
                last_referenced_at=self.clock().isoformat(),
                scope="conversation",
                expiration_policy=f"turn_window:{self.max_turns}",
                confidence_decay=self.confidence_decay,
                turn_index=prior.lifecycle.turn_index + 1,
            ),
        )
        self.save(
            session_id,
            merged,
            user_id=user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
        )
        return self.get(
            session_id, user_id=user_id, conversation_id=conversation_id
        )

    @staticmethod
    def _make_slots(
        values: dict[str, Any] | None,
        source: ProvenanceSource,
        *,
        turn_id: str = "",
        parser_id: str = "",
    ) -> tuple[SemanticSlot, ...]:
        return tuple(
            SemanticSlot(
                name=name,
                value=value,
                value_type=type(value).__name__,
                provenance=Provenance(
                    source=source,
                    turn_id=turn_id,
                    parser_id=parser_id,
                    source_field=name,
                ),
            )
            for name, value in (values or {}).items()
        )

    @staticmethod
    def _merge_entities(
        previous: tuple[EntityReference, ...],
        current: tuple[EntityReference, ...],
        decay: float,
        min_confidence: float,
    ) -> tuple[EntityReference, ...]:
        merged: dict[tuple[str, str], EntityReference] = {}
        for entity in previous:
            inherited_confidence = entity.confidence * decay
            if inherited_confidence < min_confidence:
                continue
            inherited = replace(
                entity,
                confidence=inherited_confidence,
                provenance=replace(
                    entity.provenance,
                    source=ProvenanceSource.CONVERSATION_CONTEXT,
                    confidence=entity.provenance.confidence * decay,
                ),
            )
            merged[(entity.entity_type, entity.entity_id or str(entity.value))] = inherited
        for entity in current:
            merged[(entity.entity_type, entity.entity_id or str(entity.value))] = entity
        return tuple(merged.values())
