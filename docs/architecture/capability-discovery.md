# Capability Discovery

## Purpose

Sprint 18.5 makes Registry metadata the composition boundary between a user
goal and an executable operation:

```text
Goal
  -> Capability Search
  -> Candidate Operations
  -> Contract Match
  -> Permission Filter
  -> Cost / Reliability Optimizer
  -> Execution Plan
```

Planner discovers what Jarvis can do. It does not require a new branch for
each future integration.

## Registry Contract

An Ability may declare `operations` in `AbilityMetadata`. Each operation can
provide:

- operation name and input/output schemas;
- minimum contract version;
- permission and side-effect class;
- lifecycle state;
- implementation identity and result equivalence;
- estimated cost, latency, and network requirement;
- availability, reliability, and health reason.

Existing built-in Abilities continue to receive compatibility operation
metadata from `DEFAULT_ABILITY_OPERATIONS`. New Abilities declare their
operations in their Registry metadata.

## Discovery Policy

`CapabilityDiscovery` performs these steps in order:

1. Match the goal against Tool routing metadata and operation vocabulary.
2. Reject unsupported contract versions.
3. Reject sunset capabilities.
4. Reject operations outside the caller's allowed permission set.
5. Reject offline implementations.
6. Retain experimental and deprecated operations with explicit warnings.
7. Rank compatible candidates by confidence, availability, reliability, cost,
   latency, network use, and stable implementation identity.

The default policy is reliability-first. The same adaptive execution cost
model used by Plan optimization supplies recent availability, success rate,
latency, and cost observations.

## Audit Contract

Discovery returns a privacy-safe journal containing only operation and
implementation identifiers, decision, reason code, and confidence. It never
contains raw user content, mail bodies, contact data, tokens, or Provider
payloads.

Stable decisions are `CANDIDATE`, `REJECTED`, and `SELECTED`. Rejection reasons
include contract, permission, lifecycle, availability, and goal-match gates.

## Compatibility Boundary

Registry-driven Workspace compositions are checked operation by operation
before execution. Existing Calendar, Contacts, Mail, Memory, Reminder, Todo,
and Weather language rules remain as compatibility parsers during migration.
Abilities outside that compatibility set use Discovery-first planning.

This boundary prevents semantic regressions while allowing a newly registered
Discord, Notion, Slack, Home Assistant, or other Ability to become plannable
without modifying `RuntimePlanner`.

## Invariant

> Planner discovers capabilities from Registry metadata; integrations are not
> hardcoded into the Planner.
