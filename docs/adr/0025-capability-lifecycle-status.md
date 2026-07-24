# ADR 0025 - Capability Lifecycle Status

## Status

Proposed for a future Sprint 18 Registry migration.

## Context

Sprint 18.1 introduced capability contract-version requirements:
`min_contract`, `recommended`, `deprecated_after`, and `sunset`.

Version compatibility and lifecycle maturity are related but independent. A
capability may be compatible with the current contract while still being
experimental, or remain stable across several contract versions before it is
deprecated.

Jarvis needs an explicit extension point for capability maturity without
changing current execution behavior.

## Proposed Decision

Capability operation metadata may later declare:

```text
status: experimental | stable | deprecated | sunset
```

The normal lifecycle is:

```text
EXPERIMENTAL
  -> STABLE
  -> DEPRECATED
  -> SUNSET
```

Lifecycle status does not replace contract-version negotiation or
`min_contract`. Core first negotiates the contract, then checks capability
version requirements, then evaluates lifecycle policy.

## State Semantics

### Experimental

- Execution remains allowed when every existing permission, validation,
  verification, and idempotency check passes.
- Core emits `capability.experimental.executed` Telemetry.
- Developer logs may display `Experimental Capability`.
- User responses and TTS do not mention experimental status.
- Experimental status never weakens permission or confirmation requirements.

### Stable

- Normal production behavior.
- No lifecycle-specific user message or Telemetry is required.
- Promotion criteria should be measurable and recorded.

### Deprecated

- Execution may remain allowed until its sunset policy is reached.
- Core emits a structured deprecation warning and migration target when one is
  registered.
- Raw provider errors and sensitive inputs remain excluded from lifecycle
  events.

### Sunset

- New execution is blocked before an Ability or Provider is called.
- Core returns a stable lifecycle error and an available replacement
  capability when registered.
- Previously journaled tasks remain readable and replay-safe; sunset does not
  erase history.

## Promotion Contract

Promotion from Experimental to Stable should eventually require Registry-owned
evidence such as:

```text
minimum successful executions
maximum failure rate
verification coverage
permission review
schema stability window
owner approval
```

Promotion is an explicit metadata change. Telemetry must not silently promote a
capability.

## Telemetry Contract

The future experimental event should contain only:

```text
capability
operation
contract_version
provider_kind
success
latency_bucket
error_code
```

It must not contain raw input, email addresses, message bodies, OAuth tokens,
provider payloads, or unmasked user data.

## Transition Rules

- Normal transitions move forward through the lifecycle.
- A rollback from Stable to Experimental requires an explicit ADR or incident
  record.
- Deprecated may return to Stable only through an explicit reviewed decision.
- Sunset is terminal for new execution; replacement uses a new capability or a
  new compatible operation version.
- Lifecycle changes invalidate Registry metadata caches but do not alter an
  already confirmed draft or permission snapshot.

## Future Implementation TODO

1. Add `CapabilityLifecycleStatus` to operation-level Registry metadata.
2. Add lifecycle evaluation after the capability version gate.
3. Publish privacy-safe experimental and deprecated Telemetry events.
4. Add replacement-capability metadata and user-facing sunset mapping.
5. Add promotion evidence storage and an explicit review command.
6. Add transition validation and lifecycle audit events to Execution Journal.

## Consequences

- Capability maturity becomes visible without coupling it to contract versions.
- Experimental operations can collect production Telemetry without disrupting
  the user experience.
- Deprecation and sunset become planned Registry policy rather than scattered
  runtime conditions.
- No runtime behavior changes until this ADR is accepted and implemented.
