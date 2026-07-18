from jarvis.abilities.native.contacts.ability import ContactAbility


def register(registry, repository=None):
    """Register Contact Ability into an AbilityRegistry."""
    registry.register(ContactAbility(repository=repository))
    return registry
