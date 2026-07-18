"""Todo Ability registry helper."""

from jarvis.abilities.native.todo.ability import TodoAbility


def register(registry, repository=None):
    """Register TodoAbility."""
    ability = TodoAbility(repository=repository)
    registry.register(ability)
    return ability
