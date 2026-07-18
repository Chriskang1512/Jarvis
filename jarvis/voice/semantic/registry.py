"""Compatibility exports for semantic entity registry."""

from jarvis.voice.semantic.entity_resolver import (
    EntityRegistry,
    KnownEntity,
    KnownPeopleResolver,
    KnownPlaceResolver,
    ResolverRegistry,
)

__all__ = [
    "EntityRegistry",
    "KnownEntity",
    "KnownPeopleResolver",
    "KnownPlaceResolver",
    "ResolverRegistry",
]
