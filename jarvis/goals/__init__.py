"""Goal-oriented context foundation for Jarvis v1.4."""

from jarvis.goals.context_engine import (
    ContextKey,
    ConversationContextEngine,
    TurnContext,
)
from jarvis.goals.models import (
    EntityReference,
    ContextLifecycle,
    GoalConstraint,
    GoalSpecification,
    LanguageContext,
    PreviousResultContext,
    Provenance,
    ProvenanceSource,
    SemanticContext,
    SemanticSlot,
    SuccessCriterion,
    TemporalContext,
)
from jarvis.goals.parser import GoalParseResult, GoalParser

__all__ = [
    "ConversationContextEngine",
    "ContextKey",
    "ContextLifecycle",
    "EntityReference",
    "GoalConstraint",
    "GoalParseResult",
    "GoalParser",
    "GoalSpecification",
    "LanguageContext",
    "PreviousResultContext",
    "Provenance",
    "ProvenanceSource",
    "SemanticContext",
    "SemanticSlot",
    "SuccessCriterion",
    "TemporalContext",
    "TurnContext",
]
