from jarvis.abilities.native.calendar.ability import CalendarAbility


def register(registry, provider=None):
    """Register Calendar Ability into an AbilityRegistry."""
    ability = CalendarAbility(provider=provider)
    registry.register(ability)
    return ability
