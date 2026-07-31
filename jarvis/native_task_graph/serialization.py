"""Forward-compatible JSON serialization for NativeTaskGraph."""

from __future__ import annotations

import json
from datetime import datetime

from jarvis.native_task_graph.models import *


class NativeTaskGraphSerializer:
    SCHEMA_VERSION = "1.0"

    @classmethod
    def to_dict(cls, graph: NativeTaskGraph) -> dict:
        return {
            "schemaVersion": graph.schema_version,
            "graphId": graph.graph_id,
            "goalId": graph.goal_id,
            "conversationId": graph.conversation_id,
            "version": graph.version,
            "nodes": [node_to_dict(node) for node in graph.nodes],
            "edges": [edge_to_dict(edge) for edge in graph.edges],
            "outputs": [graph_output_to_dict(output) for output in graph.outputs],
            "metadata": mutable_projection(graph.metadata),
            "executionPolicy": execution_policy_to_dict(graph.execution_policy),
            "createdAt": graph.created_at.isoformat(),
            "updatedAt": graph.updated_at.isoformat(),
        }

    @classmethod
    def to_json(cls, graph: NativeTaskGraph, *, indent=None) -> str:
        return json.dumps(
            cls.to_dict(graph),
            ensure_ascii=False,
            sort_keys=True,
            indent=indent,
        )

    @classmethod
    def from_dict(cls, value: dict) -> NativeTaskGraph:
        # Unknown fields are intentionally ignored for forward compatibility.
        return NativeTaskGraph(
            graph_id=str(value.get("graphId", "")),
            goal_id=str(value.get("goalId", "")),
            conversation_id=str(value.get("conversationId", "")),
            version=int(value.get("version", 1)),
            nodes=tuple(node_from_dict(item) for item in value.get("nodes", ())),
            edges=tuple(edge_from_dict(item) for item in value.get("edges", ())),
            outputs=tuple(
                graph_output_from_dict(item) for item in value.get("outputs", ())
            ),
            metadata=dict(value.get("metadata", {}) or {}),
            execution_policy=execution_policy_from_dict(
                value.get("executionPolicy", {}) or {}
            ),
            created_at=parse_datetime(value.get("createdAt")),
            updated_at=parse_datetime(value.get("updatedAt")),
            schema_version=str(value.get("schemaVersion", cls.SCHEMA_VERSION)),
        )

    @classmethod
    def from_json(cls, text: str) -> NativeTaskGraph:
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("NativeTaskGraph JSON must be an object.")
        return cls.from_dict(value)


def parse_datetime(value):
    if not value:
        raise ValueError("Graph timestamps are required.")
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def binding_to_dict(item):
    return {
        "sourceType": item.source_type.value,
        "sourceNodeId": item.source_node_id or None,
        "sourceKey": item.source_key or None,
        "value": mutable_projection(item.value),
        "expectedType": item.expected_type,
        "isRequired": item.is_required,
        "defaultValue": mutable_projection(item.default_value),
        "transformation": item.transformation or None,
    }


def binding_from_dict(value):
    return InputBinding(
        source_type=BindingSourceType(value["sourceType"]),
        source_node_id=str(value.get("sourceNodeId", "") or ""),
        source_key=str(value.get("sourceKey", "") or ""),
        value=value.get("value"),
        expected_type=str(value.get("expectedType", "Any")),
        is_required=bool(value.get("isRequired", True)),
        default_value=value.get("defaultValue"),
        transformation=str(value.get("transformation", "") or ""),
    )


def output_definition_to_dict(item):
    return {
        "outputKey": item.output_key,
        "valueType": item.value_type,
        "isRequired": item.is_required,
        "artifactType": item.artifact_type or None,
        "description": item.description or None,
        "retentionPolicy": item.retention_policy.value,
    }


def output_definition_from_dict(value):
    return OutputDefinition(
        output_key=str(value["outputKey"]),
        value_type=str(value["valueType"]),
        is_required=bool(value.get("isRequired", True)),
        artifact_type=str(value.get("artifactType", "") or ""),
        description=str(value.get("description", "") or ""),
        retention_policy=RetentionPolicy(
            value.get("retentionPolicy", RetentionPolicy.TRANSIENT.value)
        ),
    )


def node_to_dict(item):
    return {
        "nodeId": item.node_id,
        "nodeType": item.node_type.value,
        "capabilityId": item.capability_id or None,
        "operation": item.operation or None,
        "displayName": item.display_name or None,
        "description": item.description or None,
        "inputs": {
            key: binding_to_dict(value) for key, value in sorted(item.inputs.items())
        },
        "outputs": {
            key: output_definition_to_dict(value)
            for key, value in sorted(item.outputs.items())
        },
        # Projection only. Edges remain the source of truth.
        "dependencies": list(item.dependencies),
        "requiredInputs": list(item.required_inputs),
        "permissionRequirement": item.permission_requirement.value,
        "retryPolicy": {
            "maxAttempts": item.retry_policy.max_attempts,
            "delaySeconds": item.retry_policy.delay_seconds,
            "maxDelaySeconds": item.retry_policy.max_delay_seconds,
            "backoffStrategy": item.retry_policy.backoff_strategy.value,
            "retryableErrorCodes": list(item.retry_policy.retryable_error_codes),
            "retryableCategories": list(
                item.retry_policy.retryable_categories
            ),
            "jitter": item.retry_policy.jitter,
            "providerFallbackAllowed": (
                item.retry_policy.provider_fallback_allowed
            ),
        },
        "verificationPolicy": {
            "verificationLevel": item.verification_policy.verification_level.value,
            "requiredEvidence": list(item.verification_policy.required_evidence),
            "minimumConfidence": item.verification_policy.minimum_confidence,
            "readBackCapabilityId": item.verification_policy.read_back_capability_id
            or None,
        },
        "failurePolicy": {
            "action": item.failure_policy.action.value,
            "fallbackCapabilityId": item.failure_policy.fallback_capability_id or None,
        },
        "metadata": mutable_projection(item.metadata),
    }


def node_from_dict(value):
    retry = value.get("retryPolicy", {}) or {}
    verification = value.get("verificationPolicy", {}) or {}
    failure = value.get("failurePolicy", {}) or {}
    return TaskNode(
        node_id=str(value["nodeId"]),
        node_type=NodeType(value["nodeType"]),
        capability_id=str(value.get("capabilityId", "") or ""),
        operation=str(value.get("operation", "") or ""),
        display_name=str(value.get("displayName", "") or ""),
        description=str(value.get("description", "") or ""),
        inputs={
            key: binding_from_dict(item)
            for key, item in dict(value.get("inputs", {})).items()
        },
        outputs={
            key: output_definition_from_dict(item)
            for key, item in dict(value.get("outputs", {})).items()
        },
        # Serialized dependencies are ignored: TaskEdge is authoritative.
        required_inputs=tuple(value.get("requiredInputs", ())),
        permission_requirement=PermissionRequirement(
            value.get("permissionRequirement", PermissionRequirement.SAFE.value)
        ),
        retry_policy=RetryPolicy(
            max_attempts=int(retry.get("maxAttempts", 1)),
            delay_seconds=float(retry.get("delaySeconds", 0.0)),
            max_delay_seconds=float(retry.get("maxDelaySeconds", 10.0)),
            backoff_strategy=BackoffStrategy(
                retry.get("backoffStrategy", BackoffStrategy.NONE.value)
            ),
            retryable_error_codes=tuple(retry.get("retryableErrorCodes", ())),
            retryable_categories=tuple(
                retry.get("retryableCategories", ())
            ),
            jitter=bool(retry.get("jitter", False)),
            provider_fallback_allowed=bool(
                retry.get("providerFallbackAllowed", False)
            ),
        ),
        verification_policy=VerificationPolicy(
            verification_level=VerificationLevel(
                verification.get(
                    "verificationLevel", VerificationLevel.NONE.value
                )
            ),
            required_evidence=tuple(verification.get("requiredEvidence", ())),
            minimum_confidence=float(verification.get("minimumConfidence", 0.0)),
            read_back_capability_id=str(
                verification.get("readBackCapabilityId", "") or ""
            ),
        ),
        failure_policy=FailurePolicy(
            action=FailureAction(
                failure.get("action", FailureAction.FAIL_GRAPH.value)
            ),
            fallback_capability_id=str(
                failure.get("fallbackCapabilityId", "") or ""
            ),
        ),
        metadata=dict(value.get("metadata", {}) or {}),
    )


def edge_to_dict(item):
    return {
        "edgeId": item.edge_id,
        "sourceNodeId": item.source_node_id,
        "targetNodeId": item.target_node_id,
        "edgeType": item.edge_type.value,
        "condition": item.condition or None,
        "metadata": mutable_projection(item.metadata),
    }


def edge_from_dict(value):
    return TaskEdge(
        edge_id=str(value["edgeId"]),
        source_node_id=str(value["sourceNodeId"]),
        target_node_id=str(value["targetNodeId"]),
        edge_type=EdgeType(value.get("edgeType", EdgeType.DEPENDENCY.value)),
        condition=str(value.get("condition", "") or ""),
        metadata=dict(value.get("metadata", {}) or {}),
    )


def graph_output_to_dict(item):
    return {
        "outputId": item.output_id,
        "sourceNodeId": item.source_node_id,
        "sourceOutputKey": item.source_output_key,
        "outputType": item.output_type,
        "displayName": item.display_name or None,
        "isPrimary": item.is_primary,
        "artifactPolicy": item.artifact_policy.value,
    }


def graph_output_from_dict(value):
    return GraphOutput(
        output_id=str(value["outputId"]),
        source_node_id=str(value["sourceNodeId"]),
        source_output_key=str(value["sourceOutputKey"]),
        output_type=str(value["outputType"]),
        display_name=str(value.get("displayName", "") or ""),
        is_primary=bool(value.get("isPrimary", False)),
        artifact_policy=ArtifactPolicy(
            value.get("artifactPolicy", ArtifactPolicy.NONE.value)
        ),
    )


def execution_policy_to_dict(item):
    return {
        "executionMode": item.execution_mode.value,
        "maxNodeCount": item.max_node_count,
        "maxExecutionDurationSeconds": item.max_execution_duration_seconds,
        "allowParallelExecution": item.allow_parallel_execution,
        "allowReplan": item.allow_replan,
        "allowPartialCompletion": item.allow_partial_completion,
        "stopOnFailure": item.stop_on_failure,
        "permissionStrategy": item.permission_strategy.value,
    }


def execution_policy_from_dict(value):
    return GraphExecutionPolicy(
        execution_mode=ExecutionMode(
            value.get("executionMode", ExecutionMode.SEQUENTIAL.value)
        ),
        max_node_count=int(value.get("maxNodeCount", 50)),
        max_execution_duration_seconds=float(
            value.get("maxExecutionDurationSeconds", 300.0)
        ),
        allow_parallel_execution=bool(value.get("allowParallelExecution", False)),
        allow_replan=bool(value.get("allowReplan", False)),
        allow_partial_completion=bool(value.get("allowPartialCompletion", False)),
        stop_on_failure=bool(value.get("stopOnFailure", True)),
        permission_strategy=PermissionStrategy(
            value.get("permissionStrategy", PermissionStrategy.BATCH.value)
        ),
    )
