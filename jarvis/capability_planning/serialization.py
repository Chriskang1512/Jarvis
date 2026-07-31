"""JSON contracts for capability snapshots and planner results."""

from __future__ import annotations

import json
from datetime import datetime

from jarvis.capability_planning.models import *
from jarvis.native_task_graph import (
    BindingSourceType,
    NativeTaskGraphSerializer,
    PermissionRequirement,
    VerificationLevel,
)


def snapshot_to_dict(snapshot):
    return {
        "snapshotId": snapshot.snapshot_id,
        "createdAt": snapshot.created_at.isoformat(),
        "schemaVersion": snapshot.schema_version,
        "capabilities": [
            capability_to_dict(item) for item in snapshot.capabilities
        ],
        "environmentConstraints": dict(snapshot.environment_constraints),
        "disabledCapabilities": [
            {"capabilityId": item.capability_id, "reason": item.reason}
            for item in snapshot.disabled_capabilities
        ],
        "registryHash": snapshot.registry_hash,
    }


def snapshot_to_json(snapshot):
    return json.dumps(
        snapshot_to_dict(snapshot),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def snapshot_from_dict(value):
    capabilities = tuple(
        capability_from_dict(item) for item in value.get("capabilities", ())
    )
    return CapabilityRegistrySnapshot(
        snapshot_id=str(value["snapshotId"]),
        created_at=parse_datetime(value["createdAt"]),
        schema_version=str(value.get("schemaVersion", "1.0")),
        capabilities=capabilities,
        environment_constraints=dict(value.get("environmentConstraints", {})),
        disabled_capabilities=tuple(
            DisabledCapability(
                str(item["capabilityId"]), str(item.get("reason", ""))
            )
            for item in value.get("disabledCapabilities", ())
        ),
        registry_hash=str(value.get("registryHash", "")),
    )


def snapshot_from_json(text):
    return snapshot_from_dict(json.loads(text))


def capability_from_dict(value):
    execution = value.get("executionCharacteristics", {})
    verification = value.get("verificationSupport", {})
    provider = value.get("providerRequirements", {})
    return CapabilityDescriptor(
        capability_id=str(value["capabilityId"]),
        version=str(value["version"]),
        display_name=str(value["displayName"]),
        description=str(value.get("description", "")),
        domain=str(value["domain"]),
        operation=str(value["operation"]),
        input_schema=tuple(
            CapabilityInputDefinition(
                name=str(item["name"]),
                value_type=str(item["valueType"]),
                is_required=bool(item.get("isRequired", False)),
                description=str(item.get("description", "")),
                default_value=item.get("defaultValue"),
                allowed_sources=tuple(
                    BindingSourceType(source)
                    for source in item.get("allowedSources", ())
                ),
                constraints=dict(item.get("constraints", {})),
                is_sensitive=bool(item.get("isSensitive", False)),
            )
            for item in value.get("inputSchema", ())
        ),
        output_schema=tuple(
            CapabilityOutputDefinition(
                name=str(item["name"]),
                value_type=str(item["valueType"]),
                description=str(item.get("description", "")),
                is_required=bool(item.get("isRequired", True)),
                artifact_type=str(item.get("artifactType", "")),
                is_sensitive=bool(item.get("isSensitive", False)),
            )
            for item in value.get("outputSchema", ())
        ),
        permission_requirement=PermissionRequirement(
            value.get("permissionRequirement", "Safe")
        ),
        execution_characteristics=ExecutionCharacteristics(
            side_effect=str(execution.get("sideEffect", "none")),
            network_required=bool(execution.get("networkRequired", False)),
            parallel_safe=bool(execution.get("parallelSafe", False)),
            estimated_latency_ms=int(execution.get("estimatedLatencyMs", 0)),
        ),
        verification_support=VerificationSupport(
            levels=tuple(
                VerificationLevel(level)
                for level in verification.get("levels", ("Schema",))
            ),
            read_back_capability_id=str(
                verification.get("readBackCapabilityId", "")
            ),
        ),
        provider_requirements=ProviderRequirements(
            network_required=bool(provider.get("networkRequired", False)),
            required_features=tuple(provider.get("requiredFeatures", ())),
        ),
        tags=tuple(value.get("tags", ())),
        availability=Availability(value.get("availability", "Available")),
        metadata=dict(value.get("metadata", {})),
    )


def planner_result_to_dict(result):
    diagnostics = result.diagnostics
    return {
        "status": result.status.value,
        "graph": NativeTaskGraphSerializer.to_dict(result.graph)
        if result.graph
        else None,
        "plannerType": result.planner_type.value,
        "modelId": result.model_id,
        "capabilitySnapshotId": result.capability_snapshot_id,
        "confidence": result.confidence,
        "assumptions": [
            {
                "field": item.field,
                "assumedValue": item.assumed_value,
                "reason": item.reason,
                "confidence": item.confidence,
                "source": item.source,
            }
            for item in result.assumptions
        ],
        "missingInputs": [
            {
                "capabilityId": item.capability_id,
                "field": item.field,
                "reason": item.reason,
                "isSensitive": item.is_sensitive,
            }
            for item in result.missing_inputs
        ],
        "warnings": list(result.warnings),
        "diagnostics": {
            "plannerType": diagnostics.planner_type,
            "plannerDurationMs": diagnostics.planner_duration_ms,
            "selectedCapabilities": list(diagnostics.selected_capabilities),
            "rejectedCapabilities": list(diagnostics.rejected_capabilities),
            "repairCount": diagnostics.repair_count,
            "validationIssues": list(diagnostics.validation_issues),
            "capabilitySnapshotId": diagnostics.capability_snapshot_id,
            "registryHash": diagnostics.registry_hash,
            "routingReason": diagnostics.routing_reason,
            "confidence": diagnostics.confidence,
            "inputTokens": diagnostics.input_tokens,
            "outputTokens": diagnostics.output_tokens,
            "aiFailure": diagnostics.ai_failure,
            "inputLength": diagnostics.input_length,
            "inputHash": diagnostics.input_hash,
            "entitySummary": [
                dict(item) for item in diagnostics.entity_summary
            ],
        }
        if diagnostics
        else None,
        "successCriteriaMappings": [
            {
                "criterionId": item.criterion_id,
                "nodeId": item.node_id,
                "outputKey": item.output_key,
                "verificationLevel": item.verification_level.value,
            }
            for item in result.success_criteria_mappings
        ],
        "failure": {
            "reason": result.failure.reason.value,
            "missingCapabilities": list(result.failure.missing_capabilities),
            "missingNodes": list(result.failure.missing_nodes),
            "suggestedCapabilities": list(
                result.failure.suggested_capabilities
            ),
            "recoverable": result.failure.recoverable,
        }
        if result.failure
        else None,
        "createdAt": result.created_at.isoformat(),
    }


def planner_result_to_json(result):
    return json.dumps(
        planner_result_to_dict(result),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def planner_result_from_dict(value):
    diagnostic = value.get("diagnostics")
    failure = value.get("failure")
    return PlannerResult(
        status=PlannerStatus(value["status"]),
        graph=NativeTaskGraphSerializer.from_dict(value["graph"])
        if value.get("graph")
        else None,
        planner_type=PlannerType(value["plannerType"]),
        model_id=str(value.get("modelId", "")),
        capability_snapshot_id=str(value["capabilitySnapshotId"]),
        confidence=float(value.get("confidence", 0.0)),
        assumptions=tuple(
            Assumption(
                str(item["field"]),
                item.get("assumedValue"),
                str(item.get("reason", "")),
                float(item.get("confidence", 0.0)),
                str(item.get("source", "")),
            )
            for item in value.get("assumptions", ())
        ),
        missing_inputs=tuple(
            MissingInput(
                str(item["capabilityId"]),
                str(item["field"]),
                str(item.get("reason", "")),
                bool(item.get("isSensitive", False)),
            )
            for item in value.get("missingInputs", ())
        ),
        warnings=tuple(value.get("warnings", ())),
        diagnostics=PlannerDiagnostics(
            planner_type=str(diagnostic["plannerType"]),
            planner_duration_ms=int(diagnostic.get("plannerDurationMs", 0)),
            selected_capabilities=tuple(
                diagnostic.get("selectedCapabilities", ())
            ),
            rejected_capabilities=tuple(
                diagnostic.get("rejectedCapabilities", ())
            ),
            repair_count=int(diagnostic.get("repairCount", 0)),
            validation_issues=tuple(diagnostic.get("validationIssues", ())),
            capability_snapshot_id=str(
                diagnostic.get("capabilitySnapshotId", "")
            ),
            registry_hash=str(diagnostic.get("registryHash", "")),
            routing_reason=str(diagnostic.get("routingReason", "")),
            confidence=float(diagnostic.get("confidence", 0.0)),
            input_tokens=int(diagnostic.get("inputTokens", 0)),
            output_tokens=int(diagnostic.get("outputTokens", 0)),
            ai_failure=str(diagnostic.get("aiFailure", "")),
            input_length=int(diagnostic.get("inputLength", 0)),
            input_hash=str(diagnostic.get("inputHash", "")),
            entity_summary=tuple(
                dict(item)
                for item in diagnostic.get("entitySummary", ())
            ),
        )
        if diagnostic
        else None,
        success_criteria_mappings=tuple(
            SuccessCriterionMapping(
                str(item["criterionId"]),
                str(item["nodeId"]),
                str(item["outputKey"]),
                VerificationLevel(item["verificationLevel"]),
            )
            for item in value.get("successCriteriaMappings", ())
        ),
        failure=PlannerFailure(
            reason=PlannerFailureReason(failure["reason"]),
            missing_capabilities=tuple(
                failure.get("missingCapabilities", ())
            ),
            missing_nodes=tuple(failure.get("missingNodes", ())),
            suggested_capabilities=tuple(
                failure.get("suggestedCapabilities", ())
            ),
            recoverable=bool(failure.get("recoverable", False)),
        )
        if failure
        else None,
        created_at=parse_datetime(value["createdAt"]),
    )


def planner_result_from_json(text):
    return planner_result_from_dict(json.loads(text))


def parse_datetime(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
