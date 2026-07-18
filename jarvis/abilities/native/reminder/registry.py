from jarvis.abilities.native.reminder.ability import ReminderAbility


def register(registry, engine=None):
    """Register Reminder Ability into an AbilityRegistry."""
    ability = ReminderAbility(engine=engine)
    registry.register(ability)
    return ability
