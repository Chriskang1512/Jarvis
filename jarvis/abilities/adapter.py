from jarvis.abilities.metadata import AbilityType
from jarvis.abilities.result import AbilityResult
from jarvis.permissions import PermissionLevel
from jarvis.tools.contracts import ToolMetadata, ToolResult


class AbilityToolAdapter:
    """Expose an Ability through the existing ToolRouter and Dispatcher path."""

    def __init__(self, ability):
        """Create a tool-compatible wrapper for one ability."""
        self.ability = ability
        self.metadata = create_tool_metadata(ability.metadata)

    def execute(self, input_data):
        """Execute the wrapped ability and return a ToolResult."""
        result = self.ability.execute(input_data)

        if not isinstance(result, AbilityResult):
            result = AbilityResult(success=True, data=result)

        error = result.error

        if not result.success and error == "":
            data = getattr(result, "data", None)

            if hasattr(data, "to_natural_language"):
                error = data.to_natural_language()

        return ToolResult(
            tool_name=self.metadata.name,
            success=result.success,
            output=result,
            error=error,
        )


def create_tool_metadata(metadata):
    """Translate ability metadata to tool metadata without changing Core."""
    is_safe = metadata.permission == PermissionLevel.SAFE

    return ToolMetadata(
        name=metadata.id,
        description=metadata.description,
        version=metadata.version,
        domain=f"ability.{normalize_ability_type(metadata.type)}",
        permission_level=metadata.permission,
        safety_level=metadata.permission,
        safe=is_safe,
        priority=priority_to_int(getattr(metadata, "priority", "normal")),
        priority_label=getattr(metadata, "priority", "normal"),
        provider=getattr(metadata, "provider", ""),
        capability=f"ability.{metadata.id}",
        aliases=list(metadata.aliases),
        supported_intents=list(metadata.supported_intents),
        examples=list(metadata.examples),
        input_mode="text",
        input_prefixes=list(metadata.input_prefixes),
        allow_empty_input=False,
        route_confidence=metadata.route_confidence,
    )


def normalize_ability_type(ability_type):
    """Return a stable type string for enum or string metadata."""
    if isinstance(ability_type, AbilityType):
        return ability_type.value

    return str(ability_type).lower()


def priority_to_int(priority):
    """Return sortable priority value."""
    normalized = str(priority or "normal").lower()

    if normalized == "high":
        return 100

    if normalized == "low":
        return -100

    return 0
