# Conversation Resolver

## Ownership Rule

> Conversation state belongs to RuntimeTask, never to an Ability.

An Ability accepts input, performs one operation, and returns a result. It must
not retain selections, questions, drafts, confirmation state, or resume state
between calls.

## Runtime Model

`RuntimeTask.conversation_context` owns the pending question, privacy-safe
clarification history, selected entities, pending artifacts, and confirmation
state.

`PendingArtifact` stores type, ID, fingerprint, creation time, and verification
state. Its in-memory payload is excluded from diagnostics. Logs and task
serialization expose artifact fingerprints and selected entity keys only.

## Resolver Contract

`ConversationResolver` is the only component that creates, answers, advances,
or clears questions and artifacts. `ConversationSession` remains a voice
lifecycle facade for compatibility, but its pending and selection APIs read and
write the active RuntimeTask context.

The Dispatcher injects Runtime-owned mail selections into each Mail Ability
call. Mail Ability therefore has no recent-message or selected-message cache.
Direct Dispatcher calls use a Dispatcher-owned RuntimeTask with the same
contract.

## Clarification And Confirmation

Clarification stores candidate identifiers and a `PendingQuestion` before
waiting. The Resolver interprets the answer and records only its kind in
clarification history. Confirmation freezes the preview as a
`PendingArtifact`; approval resumes the exact checkpointed input, while
rejection cancels the task without invoking the Ability.

## Cleanup And Privacy

Terminal task transitions clear questions, selections, and pending artifacts.
The voice session also clears its conversation RuntimeTask when the follow-up
window closes. Confirmed actions remove their draft artifact while retaining
read selections until the active conversation itself ends.

Checkpoint snapshots retain the in-memory ConversationContext for resume.
Checkpoint fingerprints include only question kinds, selection keys, and
artifact fingerprints, never mail bodies, addresses, contact payloads, or raw
user input.
