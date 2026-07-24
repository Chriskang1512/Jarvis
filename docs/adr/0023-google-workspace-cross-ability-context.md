# ADR 0023 - Google Workspace Cross-Ability Context

## Status

Accepted for Jarvis v0.6.0 Sprint 17.6.

## Context

Calendar, Contacts, and Gmail already expose provider-independent Ability
contracts. A Workspace request can require more than one of them:

```text
우수 연락처 찾아서 테스트 메일 보내줘
아야에게 내일 오후 3시 일정 메일로 보내줘
```

Passing Google API objects between Abilities would couple the Planner to
providers. Reparsing the original sentence after confirmation could also
change the recipient or message body.

## Decision

The Planner creates ordered steps with explicit dependencies. Completed
read-only steps publish a minimal normalized value into the RuntimeTask
context:

```text
Contacts.get -> {display_name, emails, id}
Calendar.list -> {title, date, time, id}
```

The Dispatcher resolves only the dependent `Mail.send` input from that context.
Mail Ability then creates its normal immutable pending draft and returns
`confirm_required`.

Google API resources remain inside their providers. The task context contains
no raw provider response and no mail body from Gmail.

## Safety Invariants

- Contacts and Calendar lookup are read-only.
- A cross-Ability plan cannot bypass Mail Ability validation.
- Gmail send is never called before explicit confirmation.
- Confirmation executes the exact frozen draft without reparsing.
- Missing or invalid recipient data fails closed.
- Duplicate pending-action fingerprints remain blocked.
- Mail list/search are read-only. An explicit message-open action may remove
  only Gmail's `UNREAD` label through the provider contract.

## Consequences

- Workspace composition is deterministic and testable without Google APIs.
- The same task context mechanism can support future multi-Ability plans.
- Planner rules remain intentionally narrow; ambiguous goals still require
  clarification or the structured Intent Parser.
