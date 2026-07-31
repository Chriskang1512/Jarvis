# ADR 0035: Native TaskGraph Domain Architecture

Status: Accepted
Date: 2026-07-28

## Context

Sprint 1 normalized natural language into `GoalSpecification`. Sprint 2 needs a
stable, serializable plan definition before a planner or executor can be added.
The existing `jarvis.runtime.task.TaskGraph` contains execution-time state and
continues to support the current runtime; it is not the v1.4 plan contract.

## Decision

`jarvis.native_task_graph` is the v1.4 immutable plan-definition boundary:

`GoalSpecification -> NativeTaskGraph -> Validate -> Serialize -> Restore`

`NativeTaskGraph` describes what should be executed. It contains graph identity,
conversation and goal identity, immutable node/edge/output definitions,
metadata, policies, schema version, and timezone-aware timestamps. It contains
no running state, attempts, results, errors, or checkpoints.

A future `GraphExecutionSession` describes how one graph version is progressing.
It will own node state, attempt counts, output values, failures, permission
pauses, and checkpoints. Replaying a graph therefore creates a new session
without mutating the plan.

## Edges and dependencies

`TaskEdge` is the only source of truth for dependencies. `TaskNode.dependencies`
is a computed projection rebuilt from edges when a graph is created or restored.
Serialized dependency values are diagnostic only and are ignored on restore.

The initial execution policy is sequential, disallows parallel execution and
partial completion, stops on failure, and disables replanning.

## Binding and type safety

Bindings use explicit source kinds. Invalid combinations, such as a Literal
with a source node or a NodeOutput without one, fail during model creation.
Node outputs use `OutputDefinition` with a declared value type. Validation checks
NodeOutput and GraphOutput references and basic type compatibility before any
execution layer sees the graph.

## Validation

Validation is non-throwing and returns a structured report containing errors,
warnings, stable codes, locations, and suggested fixes. It covers identifiers,
references, cycles, the entry-root reachability model, required inputs, output
keys, type compatibility, graph outputs, and node-count limits.

The first node is the default entry node. A graph may override it with
`metadata.entryNodeId`. This makes disconnected nodes detectable while
parallel/fan-out execution remains outside v1.4's initial scope.

## Serialization

The JSON contract uses `schemaVersion: "1.0"`, string enums, explicit nulls for
optional descriptive/reference fields, and ISO-8601 timezone-aware timestamps.
Readers ignore unknown fields for forward compatibility. The contract is
intended for planner output, dashboard visualization, replay, diagnostics,
audit logs, and future execution checkpoints.

## Compatibility

The implementation is additive. It does not import or execute Ability,
Provider, Permission, `GraphExecutor`, or the existing runtime graph. Direct
Execution remains unchanged.
