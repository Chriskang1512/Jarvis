from jarvis.abilities.metadata import AbilityMetadata, AbilityType
from jarvis.permissions import PermissionLevel


class N8nBridgeAbility:
    """Placeholder bridge contract for future integration abilities."""

    metadata = AbilityMetadata(
        id="n8n_bridge",
        name="n8n_bridge",
        type=AbilityType.INTEGRATION,
        permission=PermissionLevel.CONFIRM,
        description="Route integration ability calls through an n8n workflow bridge.",
        input_schema={
            "type": "object",
            "properties": {
                "workflow": {"type": "string"},
                "payload": {"type": "object"},
            },
            "required": ["workflow", "payload"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "result": {"type": "object"},
            },
            "required": ["status"],
        },
    )

    def execute(self, input_data):
        """Fail closed until the n8n bridge transport is configured."""
        raise NotImplementedError("n8n bridge transport is not configured.")
