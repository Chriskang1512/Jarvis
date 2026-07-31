"""Adapter from existing AbilityRegistry contracts to planner snapshots."""

from __future__ import annotations

from jarvis.capability_planning.models import (
    Availability,
    CapabilityDescriptor,
    CapabilityInputDefinition,
    CapabilityOutputDefinition,
    CapabilityRegistrySnapshot,
    DisabledCapability,
    ExecutionCharacteristics,
    ProviderRequirements,
    VerificationSupport,
)
from jarvis.native_task_graph import (
    BindingSourceType,
    PermissionRequirement,
    VerificationLevel,
)


CANONICAL_OPERATION_IDS = {
    "weather.query": "weather.get_forecast",
    "calendar.list": "calendar.search_events",
    "calendar.create": "calendar.create_event",
    "calendar.update": "calendar.update_event",
    "calendar.delete": "calendar.delete_event",
    "contacts.get": "contacts.search",
    "contacts.list": "contacts.search",
    "mail.search": "mail.search",
    "mail.send": "mail.send",
    "reminder.create": "reminder.create",
}

READ_BACK_CAPABILITIES = {
    "calendar.create_event": "calendar.search_events",
    "calendar.update_event": "calendar.search_events",
    "mail.send": "mail.search",
    "reminder.create": "reminder.list",
}


DEFAULT_SCHEMAS = {
    "weather.get_forecast": (
        (
            CapabilityInputDefinition(
                "location",
                "string",
                True,
                allowed_sources=(
                    BindingSourceType.CONTEXT_SLOT,
                    BindingSourceType.GOAL_INPUT,
                    BindingSourceType.USER_PREFERENCE,
                    BindingSourceType.LITERAL,
                ),
            ),
            CapabilityInputDefinition(
                "date",
                "string",
                True,
                allowed_sources=(
                    BindingSourceType.CONTEXT_SLOT,
                    BindingSourceType.GOAL_INPUT,
                    BindingSourceType.LITERAL,
                ),
            ),
        ),
        (CapabilityOutputDefinition("forecast", "WeatherReport"),),
    ),
    "calendar.search_events": (
        (
            CapabilityInputDefinition("date", "string", True),
            CapabilityInputDefinition("time_range", "string", False),
        ),
        (CapabilityOutputDefinition("events", "CalendarEventList"),),
    ),
    "calendar.create_event": (
        (
            CapabilityInputDefinition("date", "string", True),
            CapabilityInputDefinition("time", "string", True),
            CapabilityInputDefinition("title", "string", True),
            CapabilityInputDefinition("participants", "ContactList", False),
        ),
        (
            CapabilityOutputDefinition(
                "event", "CalendarEvent", artifact_type="CalendarEventRef"
            ),
        ),
    ),
    "calendar.update_event": (
        (
            CapabilityInputDefinition("date", "string", True),
            CapabilityInputDefinition("title", "string", True),
            CapabilityInputDefinition("time", "string", True),
            CapabilityInputDefinition("event_id", "string", False),
            CapabilityInputDefinition(
                "event", "CalendarEventList", False
            ),
        ),
        (
            CapabilityOutputDefinition(
                "event", "CalendarEvent", artifact_type="CalendarEventRef"
            ),
        ),
    ),
    "contacts.search": (
        (CapabilityInputDefinition("query", "string", True),),
        (CapabilityOutputDefinition("contacts", "ContactList"),),
    ),
    "mail.send": (
        (
            CapabilityInputDefinition("recipient", "string", True, is_sensitive=True),
            CapabilityInputDefinition("subject", "string", True),
            CapabilityInputDefinition("body", "string", True, is_sensitive=True),
        ),
        (
            CapabilityOutputDefinition(
                "message", "EmailMessage", artifact_type="EmailMessageRef"
            ),
        ),
    ),
    "reminder.create": (
        (
            CapabilityInputDefinition("datetime", "string", True),
            CapabilityInputDefinition("message", "string", True),
            CapabilityInputDefinition("should_create", "boolean", False),
        ),
        (
            CapabilityOutputDefinition(
                "reminder", "Reminder", artifact_type="ReminderRef"
            ),
        ),
    ),
    "system.condition": (
        (
            CapabilityInputDefinition("value", "Any", True),
            CapabilityInputDefinition("expression", "string", True),
        ),
        (
            CapabilityOutputDefinition("result", "boolean"),
            CapabilityOutputDefinition(
                "matched_branch",
                "string",
                description="Matched branch: true or false.",
            ),
            CapabilityOutputDefinition(
                "evidence",
                "ConditionEvidence",
                description="Structured source and comparison evidence.",
            ),
            CapabilityOutputDefinition(
                "actual_value", "Any", is_required=False
            ),
            CapabilityOutputDefinition(
                "expected_value", "Any", is_required=False
            ),
            CapabilityOutputDefinition("operator", "string"),
        ),
    ),
    "system.transform": (
        (
            CapabilityInputDefinition("source", "Any", True),
            CapabilityInputDefinition("instruction", "string", True),
        ),
        (CapabilityOutputDefinition("result", "string"),),
    ),
    "system.format_result": (
        (CapabilityInputDefinition("source", "Any", True),),
        (CapabilityOutputDefinition("result", "string"),),
    ),
}


class CapabilityRegistryAdapter:
    def create_snapshot(
        self,
        ability_registry,
        *,
        environment_constraints=None,
        include_system=True,
    ):
        descriptors = []
        disabled = []
        for operation in ability_registry.list_operations():
            descriptor = self.from_operation(operation)
            if descriptor.availability == Availability.UNAVAILABLE:
                disabled.append(
                    DisabledCapability(
                        descriptor.capability_id,
                        str(getattr(operation, "health_reason", "unavailable")),
                    )
                )
            else:
                descriptors.append(descriptor)
        if include_system:
            descriptors.extend(create_system_descriptors())
        unique = {}
        for descriptor in descriptors:
            unique.setdefault(descriptor.capability_id, descriptor)
        return CapabilityRegistrySnapshot.create(
            tuple(unique[key] for key in sorted(unique)),
            environment_constraints=environment_constraints,
            disabled_capabilities=tuple(disabled),
        )

    def from_operation(self, operation):
        original_id = str(operation.id)
        canonical_id = CANONICAL_OPERATION_IDS.get(original_id, original_id)
        domain, canonical_operation = canonical_id.split(".", 1)
        permission = normalize_permission(operation.permission)
        input_schema, output_schema = DEFAULT_SCHEMAS.get(
            canonical_id, infer_schema(operation)
        )
        availability = Availability(
            {
                "ONLINE": "Available",
                "DEGRADED": "Degraded",
                "OFFLINE": "Unavailable",
            }.get(str(operation.availability).upper(), "Unavailable")
        )
        levels = (
            VerificationLevel.EXTERNAL_READ_BACK,
            VerificationLevel.SCHEMA,
        ) if permission == PermissionRequirement.CONFIRM_REQUIRED else (
            VerificationLevel.SCHEMA,
            VerificationLevel.SEMANTIC,
        )
        return CapabilityDescriptor(
            capability_id=canonical_id,
            version=str(operation.contract_version),
            display_name=canonical_id,
            description=f"Adapted {domain} {canonical_operation} capability",
            domain=domain,
            operation=canonical_operation,
            input_schema=input_schema,
            output_schema=output_schema,
            permission_requirement=permission,
            execution_characteristics=ExecutionCharacteristics(
                side_effect=str(operation.side_effect),
                network_required=bool(operation.network_required),
                parallel_safe=bool(operation.parallel_safe),
                estimated_latency_ms=int(operation.estimated_latency_ms),
            ),
            verification_support=VerificationSupport(
                levels=levels,
                read_back_capability_id=READ_BACK_CAPABILITIES.get(
                    canonical_id, ""
                ),
            ),
            provider_requirements=ProviderRequirements(
                network_required=bool(operation.network_required)
            ),
            tags=(domain, canonical_operation),
            availability=availability,
            metadata={"adaptedFrom": original_id},
        )


def create_system_descriptors():
    result = []
    for capability_id in (
        "system.condition",
        "system.transform",
        "system.format_result",
    ):
        domain, operation = capability_id.split(".", 1)
        inputs, outputs = DEFAULT_SCHEMAS[capability_id]
        result.append(
            CapabilityDescriptor(
                capability_id=capability_id,
                version="1.0",
                display_name=capability_id,
                description=f"Built-in {operation}",
                domain=domain,
                operation=operation,
                input_schema=inputs,
                output_schema=outputs,
                tags=("system",),
            )
        )
    return tuple(result)


def infer_schema(operation):
    inputs = []
    raw = operation.input_schema if isinstance(operation.input_schema, dict) else {}
    required = set(raw.get("required", ()))
    properties = raw.get("properties", {})
    for name, value in properties.items():
        inputs.append(
            CapabilityInputDefinition(
                name=name,
                value_type=normalize_json_type(value.get("type", "Any")),
                is_required=name in required,
                description=str(value.get("description", "")),
            )
        )
    raw_output = operation.output_schema
    output_type = (
        str(raw_output)
        if isinstance(raw_output, str)
        else normalize_json_type(raw_output.get("type", "Any"))
        if isinstance(raw_output, dict)
        else "Any"
    )
    return tuple(inputs), (CapabilityOutputDefinition("result", output_type),)


def normalize_json_type(value):
    return {
        "object": "Any",
        "array": "AnyList",
        "number": "number",
        "integer": "integer",
        "boolean": "boolean",
        "string": "string",
    }.get(str(value).lower(), str(value))


def normalize_permission(value):
    normalized = str(getattr(value, "value", value)).lower()
    if normalized in {"confirm", "confirm_required"}:
        return PermissionRequirement.CONFIRM_REQUIRED
    if normalized == "restricted":
        return PermissionRequirement.RESTRICTED
    return PermissionRequirement.SAFE
