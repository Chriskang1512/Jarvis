from jarvis.abilities.integration.n8n.ability import N8nIntegrationAbility


def register(registry, bridge=None, workflow_registry=None):
    """Register n8n Integration Ability into an AbilityRegistry."""
    ability = N8nIntegrationAbility(bridge=bridge, workflow_registry=workflow_registry)
    registry.register(ability)
    return ability
