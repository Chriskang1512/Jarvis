# Changelog

## [Unreleased] - Sprint 18.1 Agent Core Planner Contract

### Added

- Sprint 18.3 Runtime Task State Machine states from planning through
  verification, completion, failure, cancellation, pause, resume, and retry.
- A single validated transition engine that blocks `RUNNING -> COMPLETED`
  unless verification occurs first.
- Privacy-safe State Transition History records designed for later Execution
  Journal projection.
- Task-local monotonic `transition_id` and stable `transition_reason` fields in
  transition history and EventBus payloads, with read-only legacy aliases.
- EventBus publication for task start, confirmation wait, pause, resume, retry,
  completion, cancellation, failure, and generic state changes.
- Per-transition Runtime checkpoints with deterministic fingerprints and
  `RecoveryDecision`-driven `FROM_STEP`, `FROM_CHECKPOINT`, and `FULL_RESTART`
  resume routing.
- Legacy `SUCCESS` compatibility after mandatory `VERIFYING`, while new Agent
  Core flows use canonical `COMPLETED`.
- Sprint 18.2 operation-level Registry metadata for schema, permission,
  lifecycle, side-effect, dependency, deduplication, and parallel policy.
- Three-level Plan validation results: `VALID`, `WARNING`, and `BLOCKED`.
- Registry schema validation, missing dependency detection, and dependency
  cycle blocking.
- Smart Optimizer rules `OPT-001` through `OPT-004` for duplicate removal,
  dependency reorder, parallel safe-read grouping, and explicit dead-step
  removal.
- Execution Cost metadata for estimated cost, latency, network use,
  implementation identity, and result equivalence.
- `OPT-005` deterministic lower-cost implementation selection with
  permission, side-effect, schema, lifecycle, and contract safety filters.
- Execution-ready `execution_target` validation and serial Plan cost estimates.
- `ONLINE`, `DEGRADED`, and `OFFLINE` implementation availability metadata.
- Reliability-first and cost-first deterministic candidate selection policies.
- A bounded adaptive Runtime Metric model for recent success rate, latency,
  cost, and availability.
- Compiler fallback to equivalent ONLINE candidates and fail-closed blocking
  when every compatible implementation is OFFLINE.
- Stable health reason codes for timeout, rate limit, authentication, network,
  server, and unknown failures.
- Structured Recovery Decisions for retry backoff, rate-limit delay, OAuth
  reauthentication, network wait, and verification-required states.
- Retry budgets: three timeout retries, five server-error retries, unlimited
  rate-limit waiting, and zero automatic authentication retries.
- Stable `BACKOFF`, `WAIT`, `REAUTH`, `FALLBACK`, and `ABORT` strategies with
  fallback behavior after retry exhaustion.
- Checkpoint-friendly serialized Recovery Decision contracts for Sprint 18.3.
- `HIGH`, `NORMAL`, and `LOW` recovery priorities with a stable Scheduler queue
  key.
- `FROM_STEP`, `FROM_CHECKPOINT`, and `FULL_RESTART` resume modes so Task State
  Machine does not interpret Health Reason.
- `NONE`, `STEP_ONLY`, `CHECKPOINT`, and `FULL` resume validation contracts
  carried by each Recovery Decision.
- Privacy-safe checkpoint fingerprints with automatic `FULL_RESTART`
  escalation when task, input, permission, schema, draft, artifact, or external
  operation identity changes.
- Health reason propagation into Validator issues and `OPT-005` audit entries.
- Rule-level Optimization Journal entries with reasons and before/after step
  IDs.
- `PlanCompiler` original validation, optimization, revalidation, and
  execution-ready boundary.
- Serializable Validator Journal snapshots with deterministic replay checks.
- Contract support declarations and version negotiation for Planner and Runtime
  components.
- A deterministic Version Adapter Registry supporting explicit multi-step
  conversion paths such as `3.0 -> 2.0 -> 1.0`.
- Fail-closed `CONTRACT_VERSION_NOT_NEGOTIABLE` handling when no common version
  or registered adapter path exists.
- Operation-level `min_contract` and `recommended` requirements checked after
  negotiation and before execution.
- Fail-closed `CAPABILITY_CONTRACT_VERSION_UNSUPPORTED` errors and structured
  below-recommended warnings.
- Capability `deprecated_after` warnings and `YYYY-MM`/`YYYY-MM-DD` sunset
  policies with deterministic clock injection.
- Fail-closed `CAPABILITY_SUNSET_REACHED` handling once a registered lifecycle
  deadline arrives.
- Versioned `GoalEnvelope`, `AgentPlan`, `PlanStep`, and `PlanBinding`
  contracts alongside the current runtime Planner.
- Fail-closed Plan validation for Registry capability resolution, dependency
  references and cycles, and external-write safety policies.
- An auditable no-op Plan Optimizer that versions plans while enforcing an
  unchanged semantic fingerprint.
- A compatibility adapter from `ExecutionPlan` and `ExecutionStep` into the
  new Agent Core contracts.

### Compatibility

- Existing Planner and RuntimeTask execution remain unchanged while the new
  contract is introduced.
- Current Ability IDs are accepted as capability owners until operation-level
  Registry metadata is migrated.

### Proposed

- ADR 0025 records the future
  `Experimental -> Stable -> Deprecated -> Sunset` capability lifecycle.
- Experimental capabilities will remain operational while emitting only
  privacy-safe Telemetry; this proposal does not change runtime behavior yet.

### Verified

- Full regression suite: `769 tests OK (skipped=2)`.

## Sprint 18.0 Agent Core Design

### Architecture

- Audited the existing Planner, RuntimeTask, Ability Registry, Permission Layer,
  conversation state, retry flow, EventBus, history, metrics, and provider
  metadata against the Agent Core target.
- Classified current components as reuse, extend/migrate, or
  deprecate/remove.
- Defined versioned Planner, schema binding, validation, and semantics-preserving
  optimization contracts.
- Defined `PAUSED`, `RESUMING`, checkpoint, permission snapshot, confirmation,
  fingerprint, and `UNKNOWN_SIDE_EFFECT` safety contracts.
- Defined an append-only, privacy-safe Execution Journal and task-history
  projections.
- Accepted ADR 0024: Agent Core Integration.

## [v0.6.0-sprint.17.6] - Google Workspace Integration Polish

### Added

- Deterministic `Contacts.get -> Mail.send` and
  `Calendar.list -> Mail.send` plans with explicit step dependencies.
- Provider-independent runtime context propagation for resolved contact emails
  and selected Calendar event details.
- Cross-Ability mail previews that freeze the resolved recipient, generated
  subject, and event body before confirmation.
- Integration tests for both Workspace plans and their no-send-before-confirm
  boundary.

### Changed

- Long subjects in recent-mail speech are compacted without modifying stored
  Gmail data.
- Selected-message summaries are bounded for predictable voice duration.
- Reading a selected unread Gmail message now removes its `UNREAD` label.
  Recent-mail list and search operations remain read-only.
- Gmail OAuth uses `gmail.modify`, which covers read, send, and message label
  updates. Existing tokens require one reauthentication.
- Gmail auth and permission failures now direct the user to OAuth
  reauthentication.

### Safety

- Contacts and Calendar reads may run before a send preview, but Gmail send is
  never called before explicit confirmation.
- Existing draft freezing, cancellation, duplicate-send blocking, sent-message
  verification, and PII-safe logging remain in force.

### Verified

- Full regression suite: `708 tests OK (skipped=2)`.

## [v0.6.0-sprint.17.5] - Google Gmail Send & Reply

### Added

- Gmail `gmail.send` OAuth scope while retaining `gmail.readonly`.
- Provider-independent `OutgoingMail` and `MailSendResult` contracts.
- `GoogleMailProvider.send_message()` and `reply_message()` with RFC 5322 MIME
  generation and Gmail thread-aware replies.
- Compose parsing for explicit addresses, Google Contacts recipients, generated
  predictable subjects, and reply context.
- Draft-first preview and confirmation flow that sends the exact stored draft.
- Per-pending-action duplicate-send fingerprints.
- Metadata-only post-send verification for recipient, subject, message ID, and
  thread ID.

### Safety

- Send and reply never call Gmail before explicit confirmation.
- Missing, invalid, email-less, and ambiguous recipients are blocked.
- Cancellation clears the pending action with zero provider calls.
- Logs contain masked recipients, subject hashes, and body lengths only.
- Sensitive preview TTS audio is discarded by the existing privacy policy.
- Delete, trash, archive, labels, attachments, forward, scheduled send, and bulk
  send remain out of scope.

### Verified

- Unit coverage includes compose parsing, address validation, Contacts
  resolution, confirmation, cancellation, reply context, duplicate blocking,
  MIME mapping, post-send verification, error contracts, and PII-safe traces.

## [v0.6.0-sprint.17.4] - Google Gmail Read Vertical Slice

### Added

- Gmail read-only OAuth scope support with
  `https://www.googleapis.com/auth/gmail.readonly`.
- `GoogleMailProvider` for Gmail `list`, `search`, and `get` read paths.
- Native Mail Ability package with `MailQuery`, `MailResult`, formatter, parser,
  and provider selection through `JARVIS_MAIL_PROVIDER`.
- Planner and AI intent registry routing for `mail.list`, `mail.search`, and
  `mail.get`.
- Manual auth script: `scripts/google_gmail_auth.py`.
- Gmail setup and manual verification documentation.

### Safety

- Gmail lists read sender and subject only by default.
- Selected message reads use internal `MailMessage` summaries; Gmail API objects
  stay inside the provider boundary.
- Send, delete, archive, label modification, and attachment download remain out
  of scope.

### Verified

- Fake Gmail API provider tests cover search hydration, empty results, selected
  message get, sender/subject/body mapping, unread labels, and attachment
  metadata.
- Mail Ability tests cover planner routing, list formatting, and ordinal
  follow-up reads.

## [v0.6.0-sprint.17.3] - Google Contacts Write & Safety

### Added

- Google Contacts write OAuth scope support with
  `https://www.googleapis.com/auth/contacts`.
- `GoogleContactsProvider.create_contact()` for confirmed Google People API
  contact creation.
- `GoogleContactsProvider.update_contact()` for confirmed phone, email, and
  birthday updates.
- `ContactQuery.external_id` so provider-native `people/...` resource names can
  flow through the Ability contract.
- Contact Ability routing to provider-backed create/update when
  `JARVIS_CONTACTS_PROVIDER=google`.

### Safety

- Google Contacts update resolves to a `people/...` resourceName before calling
  `updateContact`.
- Ambiguous partial matches stop with `contact_ambiguous`; Jarvis does not update
  the first returned contact.
- Create and update remain `confirm_required`.
- Contact write traces avoid logging raw phone or email fields.

### Verified

- Fake Google People API tests cover create, phone update, non-Google ID
  rejection, ambiguous update blocking, and confirmation gating.
- Full regression suite: `664 tests OK (skipped=2)`.

## [v0.6.0-sprint.17.2] - Google Contacts Read Vertical Slice

### Added

- Google People API read-only scope support for Contacts lookup.
- `GoogleContactsProvider` behind the existing Contact Ability result
  boundary.
- Shared Google client creation reused through `GoogleClientFactory`.
- Google People API payload mapping into internal Jarvis `Contact` objects.
- Runtime provider selection with `JARVIS_CONTACTS_PROVIDER=google`.
- Manual auth script: `scripts/google_contacts_auth.py`.
- Google Contacts setup and manual verification documentation.

### Verified

- Fake Google People API provider tests cover contact search, phone lookup, and
  email lookup.
- Contact Ability can route read requests to the Google provider while keeping
  writes on the existing repository path.
- Full regression suite: `642 tests OK (skipped=2)`.

### Scope

- Contacts write and sync are not implemented in Sprint 17.2.
- Calendar-specific logic stays outside the shared Google components.
- Google People API objects stay inside the provider boundary.

## [v0.6.0-sprint.17.1] - Google Calendar Write Vertical Slice

### Added

- Google Calendar `create_event`, `update_event`, and `delete_event` provider
  implementations behind the existing Calendar Provider contract.
- Google Calendar write OAuth scope support through
  `scripts/google_calendar_auth.py`.
- Google reminder override mapping for phrases such as `1시간 전에 알려줘`,
  `30분 전에 알려줘`, `10분 전에 알려줘`, and `하루 전에 알려줘`.
- Create/update/delete verification by re-reading the Google Calendar event
  before reporting success.
- Planner propagation of calendar-relative reminder offsets onto
  `calendar.create` steps for Google Calendar notification persistence.
- Safe write error codes: `EVENT_NOT_FOUND`, `CREATE_FAILED`,
  `UPDATE_FAILED`, `DELETE_FAILED`, and `REMINDER_NOT_SUPPORTED`.

### Verified

- Unit tests cover Google create/update/delete fake-client writes and reminder
  override persistence.
- Planner regression covers `내일 오후 3시에 우수 만나기 일정 잡고 1시간 전에 알려줘`.
- Existing Google read provider tests and runtime planner tests pass.

### Scope

- Write operations still require Permission Layer confirmation.
- Google Calendar is the write target; phone clock alarms are outside this
  sprint. Phone notifications are delivered through Google Calendar sync.

## [v0.6.0-sprint.17.0] - Google OAuth + Google Calendar Read Vertical Slice

### Added

- Google OAuth foundation with credential load, auth status, token refresh, and
  read-only scope validation.
- `GoogleCalendarProvider` behind the existing Calendar Provider boundary.
- Google Calendar event mapping into internal `CalendarEvent` / `CalendarResult`
  contracts.
- Provider selection through runtime calendar config and
  `JARVIS_CALENDAR_PROVIDER=google`.
- Safe Google provider error codes for auth, scope, timeout, unavailable, and
  invalid response cases.
- Manual auth script: `scripts/google_calendar_auth.py`.
- Google Calendar setup and manual verification documentation.

### Fixed

- Calendar list phrases such as `오늘 일정을 알려줘` no longer route to
  Reminder creation.
- `다음 주 일정 알려줘` routes to `calendar.list` with `next_week`.
- `다음 일정 알려줘` routes to the next upcoming event query.
- Follow-up navigation such as `다음 일정은?` remains list navigation instead
  of becoming a fresh query.
- Planner legacy mojibake tokens that caused import/runtime syntax failures
  were normalized to UTF-8-safe Korean patterns.

### Verified

- OAuth completed against the real account `lab810108@gmail.com`.
- Today query returned `2026-07-18 20:00 테스트`.
- Next week query returned `2026-07-19 15:00 테스트1`.
- Sensitive credential files are ignored by git.
- Full regression suite: `624 tests OK (skipped=2)`.

### Scope

- Google Calendar write actions remain blocked in Sprint 17.0.
- Mock Calendar remains available as the safe default provider.
- Google API objects and credentials stay inside the provider boundary.

## [v0.6.0-sprint.8] - AI Intent Parser Foundation

### Added

- `jarvis.runtime.intent` package with common Intent Parser contracts.
- `StructuredIntent`, `IntentContext`, and `IntentParseResult` models.
- Intent Registry that constrains allowed ability/action pairs.
- Rule Intent Parser for high-confidence deterministic commands.
- AI Intent Parser that accepts JSON-only structured output through the existing LLM provider abstraction.
- Hybrid Intent Parser that uses Rule first and AI fallback when rule confidence is low or missing.
- Intent metrics collector for Rule Hit %, AI Hit %, Fallback %, Clarification %, and Average Confidence.
- Intent Validator for schema, registry, required parameters, date/time format, unsupported conditionals, and forbidden URL/provider output.
- Confidence policy:
  - `>= 0.85`: executable candidate.
  - `0.70 <= confidence < 0.85`: safe reads may proceed, writes require clarification.
  - `< 0.70`: clarification/fallback.
- Planner adapter that converts structured intents into existing `ExecutionPlan` / `ExecutionStep` objects.
- Clarification plans for missing required user details such as calendar create without time.
- Intent debug traces for rule match, AI request, AI parse, validation, selected source, and latency/token metrics.
- Intent stats trace that summarizes cumulative parser routing metrics.

### Verified

- Integration health variants map to `integration.health`.
- Integration execute variants map to `integration.execute`.
- Calendar, Reminder, and Memory examples map to structured intents.
- Multi-intent AI output maps to ordered Planner steps.
- Invalid AI outputs are blocked before execution.
- Conditional execution remains unsupported and safe.
- AI provider failure falls back to high-confidence Rule parsing when possible.
- Full unit test suite passes.

### Scope

- AI structures intent only.
- Planner, Dispatcher, Permission Layer, Ability Registry, Providers, and result validation still own execution.
- No direct AI tool calling.
- No permission bypass.
- No autonomous agent loop.

## [v0.6.0-sprint.7] - Integration Bridge Foundation

### Added

- `integration_n8n` Ability for Integration Ability routing through the n8n Bridge boundary.
- Mock Integration Bridge provider for offline and test execution.
- Foundation workflows: `system.health`, `system.echo`, and `notification.test`.
- Integration request/result contracts with `conversation_id`, `session_id`, `request_id`, and `workflow_id`.
- Retry policy fields in the integration request contract.
- Provider capability metadata for health, execute, confirmation, stream, and async support.
- Integration metrics for success, failure, timeout count, and average latency.
- Voice aliases and STT corrections for common `n8n` and `system.echo` recognition variants.

### Verified

- `Planner -> Dispatcher -> Integration Ability -> Provider` path works through the Ability contract.
- `system.health` and `system.echo` execute successfully through the Mock Provider.
- Permission, validation, fail-closed unknown workflow behavior, and metrics paths are covered by tests.
- Full unit test suite passes for the Sprint 7 closure.

### Scope

- Sprint 7 closes the Integration Bridge Foundation.
- Remaining failures around phrases such as `n8n`, `system echo`, and broad automation wording are classified as Natural Language Understanding limits, not Bridge contract defects.
- The next layer should parse natural language into structured intent before Planner/Dispatcher execution.

### Next

- Add an AI Intent Parser / NLU layer:
  `STT -> user vocabulary correction -> AI Intent Parser -> structured Intent -> Planner -> Dispatcher -> Ability`.
- AI may structure the user's request, but must not bypass Registry validation, Permission Layer checks, workflow confirmation, execution, or result validation.

## [internal] - Jarvis Core v1 Complete

### Added

- ROADMAP internal milestone declaring Jarvis Core v1 complete after v0.5.0 Beta.5.3.
- Ability Era direction defining Native Abilities and Integration Abilities.
- Integration principle that external services should prefer Automation Provider -> n8n Bridge.

## [v0.5.0-beta.5.3] - Follow-up Conversation Mode

### Added

- `ConversationSession` model for wake-word conversation lifecycle tracking.
- Conversation states: `IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `FOLLOW_UP`, and `CLOSED`.
- Configurable `conversation.follow_up_timeout`, defaulting to 8 seconds.
- VoicePipeline follow-up loop that can process additional speech without repeating the wake word.
- Diagnostics events: `conversation.started`, `conversation.follow_up`, and `conversation.closed`.
- Runtime Dev Console conversation section with session ID, state, and remaining follow-up time.
- Unit tests for session creation, follow-up timeout, wake-word-free follow-up questions, idle return, and console rendering.

### Scope

- Runtime remains unaware of conversation sessions.
- Excludes memory, multi-turn context, conversation history, and AI memory.

## [v0.5.0-beta.5.2] - Voice Identity Foundation

### Added

- `VoiceProfile` contract for reusable voice identity metadata.
- `VoiceRegistry` with built-in `jarvis_default` and `friday` profiles.
- `jarvis_default` identity metadata: JARVIS-inspired original, British-inspired, low-mid/slightly-slow direction, calm/composed/witty, private butler / hotel concierge.
- Config support for top-level `tts_provider` and `voice_profile`.
- OpenAI TTS provider using `gpt-4o-mini-tts`, voice profile selection, and WAV playback.
- Voice profile config fields for voice, speed, pitch, volume, language, and reserved emotion.
- Unit tests for profile lookup, OpenAI TTS provider selection, and mocked OpenAI speech generation.

### Changed

- TTS provider selection now resolves a VoiceProfile before constructing the provider.
- `config.json` now selects OpenAI TTS with the `jarvis_default` voice profile for demo use.

### Scope

- Excludes SSML, streaming TTS, voice cloning, emotional rendering, and Edge TTS.

## [v0.5.0-beta.5.1] - TTS Debug

### Added

- VoicePipeline now prints the full response text before TTS.
- VoicePipeline now prints the exact TTS input text and character length.
- VoicePipeline now prints `len(tts_text)` after TTS playback.
- Unit test coverage for TTS debug output blocks and final length printing.
- TTS text normalizer that converts simple Markdown headings, emphasis, bullets, links, and code markers to plain text before playback.
- Unit test coverage proving the original response is preserved while TTS receives normalized text.
- Pyttsx3 playback now queues every speech chunk before one `runAndWait()` call, avoiding first-line-only playback on some Windows SAPI setups.

### Verified

- Existing Runtime and VoicePipeline tests remain compatible.

## [v0.5.0-beta.5] - OpenAI Runtime Provider

### Added

- `OpenAIChatProvider` as the explicit chat provider contract for OpenAI.
- Backward-compatible `OpenAIProvider` alias kept for existing imports.
- `chat_provider` configuration alias for selecting the active chat provider while preserving the existing `provider` key.
- Runtime Dev Console provider rendering for Mock/OpenAI visibility.
- VoicePipeline now passes the active chat provider name into the Runtime Dev Console.
- Unit tests for OpenAI provider generation using a mocked SDK response.
- Unit tests for config-based OpenAI provider selection and provider console output.

### Verified

- Mock provider remains unchanged and remains the default CI path.
- OpenAI provider tests do not call the real API.
- Runtime and Planner behavior remain unchanged.

## [v0.5.0-beta.4] - Execution Engine Enhancement

### Added

- `RetryPolicy` abstraction with default `max_retries=0`.
- `ExecutionContext` for plan-step execution metadata after planning.
- `ExecutionMetrics` for execution time, router time, dispatcher time, retry count, and fallback usage.
- `PlanStep.timeout_ms` contract for future step timeout handling.
- Reserved `CANCELLED` execution status.
- `execute_parallel(plan)` placeholder interface for future parallel execution.
- Runtime Dev Console execution metrics section for execution, retry, timeout, elapsed, and fallback visibility.
- Unit tests for retry policy, execution metrics, timeout contract, execution context, parallel placeholder, cancelled status, and console rendering.

### Verified

- Current Runtime behavior remains unchanged.
- Beta.4 execution engine tests pass.

## [v0.5.0-beta.3] - Planner Foundation

### Added

- `Plan`, `PlanStep`, and rule-based `Planner` foundation.
- Short Plan IDs such as `P-001A` for diagnostics and replay.
- PlanStep status values for PENDING, RUNNING, COMPLETED, and FAILED.
- Runtime now creates a Plan from the parsed Intent before resolving tools.
- Runtime executes Plan steps sequentially while preserving current single-step behavior.
- Runtime Dev Console version header updated to `v0.5.0 Beta.3`.
- Planner lifecycle events: `plan.created`, `plan.started`, and `plan.completed`.
- Runtime Dev Console plan rendering with plan ID, goal, steps, and step status.
- Tests for planner creation, runtime planner integration, single-step execution, empty-plan fallback, lifecycle events, and plan rendering.

### Verified

- Current Runtime behavior remains backward compatible.
- Full test suite passes.

## [v0.5.0-beta.2.5] - Runtime Dev Console

### Added

- `RuntimeDevConsole` renderer for readable RuntimeResult / RuntimeDiagnostics summaries.
- `RuntimeDevConsole.render(..., theme="simple")` API for future rich/json/minimal themes.
- Jarvis Runtime version header in the dev console.
- Runtime ID and Session ID output in the runtime dev console.
- Optional VoicePipeline runtime console output when debugging is enabled.
- `voice_main.py` now wires the default IntentRuntime so runtime flow can be inspected during voice execution.
- Unit tests for success, fallback, theme handling, Runtime/Session IDs, and VoicePipeline console output.

### Verified

- Voice runtime behavior remains unchanged when the dev console is disabled.
- Full test suite passes.

## [v0.5.0-beta.1] - Intent Runtime Foundation

### Added

- `IntentParser` and source-agnostic `IntentRuntime` for Input -> Intent -> Permission -> Router -> Dispatcher -> Response flow.
- `RuntimeContext` for text, source, language, session, user, wake word, conversation, and timestamp metadata.
- Standard `Intent` object with name, confidence, source, parameters, raw text, tool name, and permission level.
- `RuntimeResult` and `RuntimeDiagnostics` contracts for intent, permission, tool, response, diagnostics, and elapsed time.
- Immutable intent parameters for diagnostics and replay safety.
- VoicePipeline hook that uses the shared runtime before LLM fallback.
- Diagnostics fields for input text, input source, detected intent, selected tool, permission status, execution result, response, TTS output, elapsed time, and error logs.
- Generic `DiagnosticsCollector.publish()` events for runtime.started, intent.parsed, permission.checked, tool.executed, response.generated, runtime.completed, and runtime.finished.
- Confirm-required approval path through `_confirmed=True` request metadata.
- v0.5 test pack for RuntimeContext, immutable Intent, parser contract, source-agnostic runtime use, permission-before-router ordering, safe tool execution, confirm-required blocking, TTS handoff, collector events, and diagnostics rendering.

### Changed

- Time tool runtime intent is now exposed as `time.lookup`.

### Verified

- Full test suite passes.

## [v0.5.0-beta.2] - Tool Router Interface

### Added

- `jarvis.tools.router` module with `ToolRouter`, `ToolRoute`, and `RegistryToolRouter`.
- Runtime now depends on the `router.resolve(intent)` contract instead of Brain routing helpers.
- Resolve-only router test proving Runtime only needs the ToolRouter interface.

### Changed

- Shared routing helper functions moved under `jarvis.tools.router`.
- `BrainToolRouter` now reuses the shared routing helper while remaining a legacy Brain entrypoint.

### Verified

- Runtime source no longer imports `jarvis.brain.tool_router` or names `BrainToolRouter`.
- Full test suite passes.

Jarvis 프로젝트의 변경 기록입니다.

이 문서는 Keep a Changelog 형식을 참고합니다.
Jarvis 버전은 날짜가 아니라 프로젝트 완성 단계, 즉 마일스톤 기준으로 증가합니다.

## [v0.4.0] - Stable Release

### Changed

- Promoted v0.4.0-rc.1 to v0.4.0 stable.
- Runtime version updated to v0.4.0.

### Verified

- Full test suite passes.
- Planner, Execution Kernel, Result Merge, Voice, Scheduler, and Agent Runtime are stable v0.4.0 architecture layers.
- v0.5 candidates remain outside the stable release scope.

## [v0.4.0-rc.1] - Release Candidate

### Added

- v0.4.0 Release Candidate documentation
- v0.4.0 Release Note draft
- Stable public API list for Execution, Result Merge, Voice, Scheduler, and Agent Runtime
- ADR index for the v0.4 architecture documents
- v0.5 candidate list for Permission, Memory, Tool Router, Plugin System, real tool calling, OpenAI Voice Provider, audio playback, persistence, and EventBus async fan-out

### Changed

- Runtime version documented as v0.4.0-rc.1.
- v0.5 work is separated into Next / Future candidates.

### Verified

- Planner, Execution Graph, Capability Context, Result Merge, Voice Integration, Scheduler Foundation, and Agent Runtime are documented as the stable v0.4.0 architecture.
- Public APIs remain backward compatible.
- Import boundaries remain enforced by tests.
- Full test suite passes.

## [v0.4.0-beta.7] - Agent Runtime

### Added

- `jarvis.agent_runtime` package
- `AgentRuntime` for coordinating Scheduler and Execution Kernel lifecycle
- `AgentRuntimeState` enum with STOPPED, IDLE, CHECKING, RUNNING, and FAILED
- `AgentTickResult` contract for one manual runtime tick
- `ExecutionKernel` protocol defined by `run_unified()`
- explicit `start()` and `stop()` lifecycle methods
- manual `tick(now)` flow through `Scheduler.due_tasks(now)` and `Scheduler.trigger_due(now)`
- tests for lifecycle, due checks, trigger coordination, task failure isolation, runtime failure state, fixed clock behavior, and architecture boundaries
- ADR 0021 Agent Runtime Architecture

### Changed

- Runtime version updated to v0.4.0-beta.7.

### Fixed

- Agent Runtime does not import Planner, Voice, or Capabilities.
- Agent Runtime does not execute directly; Scheduler and Execution Kernel keep their separate responsibilities.

### Scope

AgentRuntime is not the executor. It is the Runtime Layer that manages the
lifecycle between Scheduler and the Execution Kernel.

Beta.7 excludes background threads, asyncio loops, daemons, autonomous planning
loops, direct Voice calls, direct Capability calls, Memory write loops, and
automatic voice playback.

## [v0.4.0-beta.6] - Scheduler Foundation

### Added

- `jarvis.scheduler` package for scheduled task lifecycle modeling
- `ScheduleRequest -> Schedule -> ScheduledTask` model flow
- `TaskState` enum with PENDING, READY, RUNNING, COMPLETED, FAILED, and CANCELLED
- one-shot `Schedule` model with `run_at`
- `ScheduledTask.is_due(now)`
- `Scheduler` protocol
- `InMemoryScheduler` / `SchedulerService`
- `InMemoryTaskStore`
- `SystemClock` and `FixedClock`
- manual `trigger_due(now)` execution through injected `ExecutionRunner.run_unified()`
- `TriggerResult` for per-task execution outcomes
- Scheduler tests for creation, due checks, cancellation, store isolation, deterministic clock, success, failure, and failure isolation
- ADR 0020 Scheduler Foundation Architecture

### Changed

- Runtime version updated to v0.4.0-beta.6.

### Fixed

- Scheduler Foundation does not import Planner, Voice, or Capabilities.
- Failed scheduled tasks do not stop later due tasks from being processed.

### Scope

Beta.6의 목표는 시간을 흐르게 만드는 것이 아니라, 예약 Task의 Lifecycle을
모델링하는 것이다.

Beta.6 excludes background threads, asyncio, cron parsing, recurring schedules,
OS schedulers, background daemons, notifications, and automatic voice playback.

## [v0.4.0-beta.5] - Voice Integration

### Added

- `VoiceService` for converting `UnifiedResult.summary` into a provider-generated `VoiceResult`
- `VoiceProvider` protocol for swappable voice synthesis providers
- Immutable `VoiceResult` contract with text, optional audio, provider, duration, and metadata
- `MockVoiceProvider` that returns the same text and no audio bytes
- OpenAI voice provider placeholder for a future implementation
- Provider package layout under `jarvis.voice.providers`
- Tests for summary-only reading, mock provider output, provider DI, immutability, and voice boundary imports
- ADR 0019 Voice Integration Architecture

### Changed

- Runtime version updated to v0.4.0-beta.5.
- Legacy `jarvis.voice.providers` module was migrated into a package while keeping existing provider imports available.

### Fixed

- Voice Integration does not import Planner, Execution Graph, or Capability modules.
- Beta.5 stops at `UnifiedResult -> VoiceService -> VoiceResult`; audio playback is explicitly deferred.

## [v0.4.0-beta.4] - Result Merge

### Added

- Result Merge layer for turning ordered capability outputs into one `UnifiedResult`
- `ResultMerger` protocol for future Default, AI, Priority, and Streaming merge implementations
- `DefaultResultMerger` deterministic implementation
- Immutable `UnifiedResult` / `UnifiedResponse` contract for Voice and UI
- Success, warning, and error merge rules
- `ExecutionGraphRunner.run_unified()` integration without embedding unified output in `ExecutionRunResult`
- Metadata for execution ID, plan ID, run status, elapsed time, node counts, result counts, warning counts, error counts, timestamp, and per-node timing
- ADR 0018 Result Merge Architecture
- Regression tests for plan order preservation, partial results after failure, Voice/UI readiness, summary behavior, immutable output, and diagnostics metadata

### Changed

- Runtime version updated to v0.4.0-beta.4.
- Beta.4 is approved for closure and Beta.5 Voice Integration may begin.

### Fixed

- Unified voice summaries report warning/error counts without mixing detailed issue text into `summary`.
- Failed nodes no longer prevent successful node outputs from appearing in the unified response.
- Capability results keep execution order through the merge layer.

### Beta.5 Entry Conditions

- Voice can read `UnifiedResult.summary`.
- UI can render `results`, `warnings`, `errors`, and `metadata`.
- Diagnostics Console can consume execution, plan, node, status, timing, and count metadata.

## [v0.4.0-beta.3] - Capability Context

### Added

- ExecutionContext for temporary per-run data
- ExecutionInputData contract with `user_input`, `previous_results`, and `execution_snapshot`
- ExecutionContext `context_version=1.0`
- Immutable execution snapshots for capabilities
- Sequential context flow from completed nodes to later nodes
- Context destruction after Runner finishes
- Diagnostics events for context updates and destruction
- ADR 0017 Execution Context Rule
- Tests proving capabilities do not import ExecutionContext

### Changed

- Runtime version updated to v0.4.0-beta.3.

### Fixed

- Runner can pass previous node results without using Memory or modifying graph structure.
- ExecutionInputData is documented as append-only and backward compatible.

## [v0.4.0-beta.2] - Execution Graph Runtime

### Added

- Execution package for validated graph runtime
- Execution Graph Runner for sequential node execution
- Execution result `execution_id` for tracking repeated plan runs
- Metadata Capability Router for metadata-driven capability intent routing
- Node lifecycle states: CREATED, RUNNING, COMPLETED, FAILED, SKIPPED
- Ordered execution result contract
- Runner diagnostics trace events and execution summary
- ADR 0016 Execution Runner Rule
- Tests for sequential execution, diagnostics, no merge, failures, and architecture boundaries

### Changed

- Runtime version updated to v0.4.0-beta.2.

### Fixed

- Runner executes plans without importing Planner, ToolRegistry, Memory, or concrete capabilities.

## [v0.4.0-beta.1] - Intent Planner Contract

### Added

- Intent Planner package for Capability Orchestration
- Stable planner contract with `plan_id`, `planner_version`, `permission_mode`, `execution_mode`, and graph output
- Planner contract `status=CREATED`
- Planner contract `graph_version=1.0`
- Reserved `graph.metadata` field for future execution estimates
- Reserved node `status`, `required`, and `confidence` fields
- Reserved edge IDs such as `edge_001`
- Capability-prefixed task IDs such as `finance_001`, `jp_002`, and `creator_003`
- PlanValidator reservation for pre-execution capability validation
- Capability metadata planning hints for capability-level intent selection
- Planner Philosophy and Planner Design Rules documentation
- ADR 0014 Intent Planner Contract
- ADR 0015 Planner Layer Rule
- Tests proving Planner selects capabilities, not tools
- Tests proving Planner does not import or instantiate concrete capabilities

### Changed

- Runtime version updated to v0.4.0-beta.1.

### Fixed

- Planner produces plans without importing ToolRegistry, Dispatcher, or Memory.

## [v0.4.0-alpha.7] - Life Capability Alpha

### Added

- Life Capability Alpha as the fifth real capability application
- `life_todo` SAFE tool
- `life_reminder` SAFE tool with Scheduler-ready output and no real scheduling
- `life_routine` SAFE tool
- `life_habit` SAFE tool
- `life_reflection` SAFE tool for summary, wins, problems, ideas, and next actions
- ADR 0012 Memory Ownership Rule
- v0.4 Alpha final architecture review addendum
- Capability Philosophy documentation
- Life prompt asset folders for todo, reminder, routine, habit, and reflection
- Tests for Life discovery, tool registration, Korean routing, Memory-adjacent reflection, Scheduler-ready reminders, and regressions

### Changed

- Runtime version updated to v0.4.0-alpha.7.
- Japanese capability metadata version normalized to alpha.

### Fixed

- Jarvis can now draft personal planning and reflection assets through the same Capability -> Tool -> Permission -> Dispatcher path without modifying Brain.

## [v0.4.0-alpha.6] - Hotel Capability Alpha

### Added

- Hotel Capability Alpha as the fourth real capability application
- `hotel_schedule_planner` SAFE tool
- `hotel_complaint_report` SAFE tool
- `hotel_complaint_manual` SAFE tool
- Hotel prompt asset folders for schedule, complaint reports, and complaint manuals
- Tests for Hotel discovery, tool registration, Korean routing, output contracts, and regressions

### Changed

- Runtime version updated to v0.4.0-alpha.6.

### Fixed

- Jarvis can now draft hospitality operations assets through the same Capability -> Tool -> Permission -> Dispatcher path without modifying Brain.

## [v0.4.0-alpha.5] - Creator Capability Alpha

### Added

- Creator Capability Alpha as the third real capability application
- `creator_lyrics` SAFE tool
- `creator_music_prompt` SAFE tool
- `creator_title` SAFE tool
- `creator_description` SAFE tool
- `creator_song_package` SAFE tool for local Creator-only orchestration
- Creator prompt asset folders for lyrics, music, thumbnail, and script prompts
- Creator sub-domain placeholders for song, video, blog, and presentation
- Creator output contracts now include project, subdomain, and asset identity
- Tests for Creator discovery, tool registration, routing, output contracts, song package, and regressions

### Changed

- Runtime version updated to v0.4.0-alpha.5.

### Fixed

- Jarvis can now generate reusable creative assets through the same Capability -> Tool -> Permission -> Dispatcher path without modifying Brain.

## [v0.4.0-alpha.4] - Finance Capability Alpha

### Added

- v0.4 Alpha Architecture Review document
- Finance Capability Alpha as the second real capability application
- `finance_compound` SAFE tool
- `finance_average_price` SAFE tool for weighted average purchase price
- `finance_profit` SAFE tool for profit/loss, return rate, and after-tax result
- `finance_portfolio` SAFE tool for allocation and diversification summaries
- `finance_exchange` SAFE tool with KRW, USD, and JPY sample conversion
- Finance capability app-style module layout with metadata, tools, prompts, and local tests folder
- Capability metadata `status` and `owner` fields
- Tool metadata `version`, `priority`, and `deprecated` fields
- Capability lifecycle APIs for enable, disable, remove, and upgrade
- Architecture tests for disabled capability routing, deprecated tools, and route priority
- Tests for Finance discovery, tool registration, Brain routing, tool execution, Japanese regression, and Core route regressions

### Changed

- Runtime version updated to v0.4.0-alpha.4.

### Fixed

- A second independent capability can now register tools through the same platform without modifying Brain.
- CLI smoke fallback cases now route through metadata: bare `finance compound`, short `exchange`, Korean time, Korean average-price, and short Japanese translate requests.

## [v0.4.0-alpha.3] - Japanese Capability Alpha

### Added

- Japanese Capability Alpha as the first real capability plugin
- Japanese capability app-style module layout with metadata, tools, prompts, and local tests folder
- `japanese_translate` SAFE tool
- `japanese_grammar` SAFE tool
- `japanese_reply` SAFE tool
- `japanese_review` SAFE tool with optional memory lookup
- ToolMetadata `examples` field for future intent matching
- Tests for Japanese discovery, tool registration, Brain routing, fallback, and existing Core route regressions

### Changed

- Runtime version updated to v0.4.0-alpha.3.

### Fixed

- Japanese assistance can now be added through Capability -> Tool -> Permission -> Dispatcher without modifying Brain.

## [v0.4.0-alpha.2] - Capability Plugin Framework

### Added

- CapabilityMetadata model and Capability protocol
- CapabilityRegistry with duplicate ID rejection, enabled lookup, and tool registration
- CapabilityLoader with automatic package discovery
- Capability skeletons for Creator, Finance, Hotel, Japanese, and Life
- Runtime capability loading before Brain Tool Router execution
- Tests for discovery, duplicate rejection, disabled exclusion, tool registration, and Brain routing through capability tools

### Changed

- Runtime version updated to v0.4.0-alpha.2.

### Fixed

- Future capability tools can register into the existing ToolRegistry without modifying Brain.

## [v0.4.0-alpha.1] - Brain Tool Routing

### Added

- BrainToolRouter for natural-language selection of safe tools
- Registry-driven routing through ToolMetadata
- Plain-language calculator, time, diagnostics, and memory-read routing
- ChatCommand pre-check that executes safe tools before falling back to the chat provider
- Tests that lock natural tool routing and LLM fallback behavior

### Changed

- Runtime version updated to v0.4.0-alpha.1.

### Fixed

- Jarvis can now use existing safe tools from normal chat input without requiring the explicit `tool` command.

## [v0.3.0-beta.7] - LLM Abstraction

### Added

- Provider-independent `jarvis.llm` package
- Common LLM provider contract with `generate()`, `generate_stream()`, and `metadata()`
- LLM provider metadata model for capability discovery
- LLMProviderFactory for provider creation from configuration
- Mock and OpenAI LLM provider adapters
- LLM diagnostics lifecycle events

### Changed

- ChatService now calls the LLM provider contract instead of a concrete provider implementation.
- Runtime provider creation now goes through the LLMProviderFactory.
- Runtime version updated to v0.3.0-beta.7.

### Fixed

- Jarvis Core no longer needs provider-specific chat calls for normal response generation.

## [v0.3.0-beta.6] - Expansion

### Added

- Plugin metadata model
- Plugin contract for local Jarvis plugins
- PluginRegistry for loaded plugin lookup
- PluginLoader for builtin plugin discovery
- Builtin echo plugin used to validate plugin tool registration
- Plugin diagnostics lifecycle events

### Changed

- Runtime now loads builtin plugins and registers plugin tools into ToolRegistry.
- Runtime version updated to v0.3.0-beta.6.

### Fixed

- Plugin tools pass through the same ToolRegistry, PermissionLayer, and ToolDispatcher as core tools.

## [v0.3.0-beta.5] - Long Memory

### Added

- Long-term Memory Store package
- Structured MemoryRecord model with category, source, tags, and timestamps
- MemoryRecord title metadata for durable record-style memories
- MemoryManager for storage and retrieval coordination
- JSON-backed Memory Store implementation
- Metadata retrieval APIs for category, tag, recent, and text search
- Memory Store diagnostics lifecycle events

### Changed

- Runtime now wires a JSON Memory Store without coupling it to VoiceSession.
- Runtime version updated to v0.3.0-beta.5.

### Fixed

- ConversationContext remains short-term and independent from persistent memory.

## [v0.3.0-beta.4] - Guardian

### Added

- PermissionLayer for metadata-driven tool authorization
- PermissionLevel values: safe, confirm, and restricted
- PermissionDecision with allowed, denied, and confirm-required statuses
- ToolMetadata permission level field
- Permission diagnostics lifecycle events

### Changed

- ToolDispatcher now checks permission before tool execution.
- Runtime version updated to v0.3.0-beta.4.

### Fixed

- Tool execution now has a single permission checkpoint before `Tool.execute()`.

## [v0.3.0-beta.3] - First Action

### Added

- Tool contract with metadata, request, and structured result models
- ToolRegistry for safe tool lookup and registration
- ToolDispatcher for tool selection and execution
- Safe built-in tools: time, calculator, diagnostics summary, and memory read
- `tool` CLI command for dispatcher-based tool execution
- Tool diagnostics lifecycle events
- Tool domain metadata and domain lookup in ToolRegistry
- Tool registry lookup commands for listing tools and domains

### Changed

- CLI bootstrap now wires ToolRegistry and ToolDispatcher without changing VoicePipeline.
- Runtime version updated to v0.3.0-beta.3.

### Fixed

- Calculator tool rejects unsupported or expensive expressions without using eval.

## [v0.3.0-beta.2] - Memory Begins

### Added

- ConversationContext for short-term session memory
- Rolling history buffer with configurable turn and token windows
- History buffer injection into chat prompts
- Conversation diagnostics events
- VoiceSession ownership of ConversationContext
- Pyttsx3 default TTS provider for local voice output

### Changed

- ChatService now keeps recent conversation turns without using long-term memory.
- Runtime version updated to v0.3.0-beta.2.

### Fixed

- Existing VoicePipeline remains compatible with session-scoped conversation memory.

## [v0.3.0-beta.1] - Voice Experience

### Added

- VoiceSession
- Streaming-ready TTS contract
- Console TTS chunk output
- Pyttsx3 TTS chunk output
- Interrupt-ready voice session flag
- Voice session ID in `voice_main.py`
- Local Piper TTS provider candidate
- Configurable TTS provider settings in `config.json`
- TTS diagnostics events for provider selection, chunks, playback, and errors

### Changed

- VoicePipeline now uses streaming-ready TTS when available.
- VoicePipeline now tracks session stage.
- VoicePipeline logs TTS streaming start and finish.
- VoicePipeline can switch TTS providers without changing pipeline code.
- Runtime version updated to v0.3.0-beta.1.

### Fixed

- Existing CLI remains available through `python main.py`.
- Existing diagnostics entry point remains available through `python diagnostics_main.py`.

## [v0.2.0-beta.2] - Metadata Console

### Added

- `diagnostics_main.py` diagnostics entry point
- `jarvis/diagnostics` module
- DiagnosticsCollector
- DiagnosticsConsole
- Session metadata
- Provider metadata
- Performance metadata
- Pipeline status metadata
- Health status metadata
- Event log rendering

### Changed

- README updated with Metadata Console architecture and usage.
- ROADMAP updated for v0.2.0-beta.2 completion.
- Runtime version updated to v0.2.0-beta.2.

### Fixed

- Diagnostics runs independently from CLI and Voice Pipeline.

## [v0.2.0-beta.1] - Voice Pipeline Foundation

### Added

- `voice_main.py` voice pipeline entry point
- `jarvis/voice` module
- WakeWordListener
- SpeechToTextProvider interface
- TextToSpeechProvider interface
- ConsoleSpeechToTextProvider
- MicrophoneSpeechToTextProvider
- ConsoleTextToSpeechProvider
- Pyttsx3TextToSpeechProvider
- VoicePipeline
- Voice stage logging
- `JARVIS_VOICE_ONCE` for one-turn voice pipeline testing

### Changed

- README updated with Voice Pipeline architecture and usage.
- ROADMAP updated for v0.2.0-beta.1 completion.
- Runtime version updated to v0.2.0-beta.1.

### Fixed

- Existing CLI remains available through `python main.py`.

## [v0.2.0-alpha.8] - The Second Brain

### Added

- ClaudeProvider
- provider=claude support
- ANTHROPIC_API_KEY loading from `.env`
- MemoryService
- MemoryProvider interface
- MockMemoryProvider
- First memory conversation
- Provider Contract Test
- ADR-0001 Core Never Knows Vendors
- v0.2.0 beta roadmap

### Changed

- Provider architecture now supports Mock, OpenAI, and Claude providers.
- README updated with Architecture Law #001.
- README updated with Claude setup and beta roadmap.
- ROADMAP updated for v0.2.0-alpha.8, beta.1, beta.2, and beta.3.
- Public `config.json` now defaults to provider=mock for safe local startup.

### Fixed

- OpenAIProvider avoids unsupported temperature parameter for gpt-5 models.
- OpenAIProvider and ClaudeProvider return friendly setup errors when API keys are missing.
- Windows console input/output uses UTF-8 when supported.

## [v0.1.0] - Project Bootstrap

### Added

- Git
- GitHub
- VS Code
- Python
- Brain
- Agent
- Memory
- Scheduler Stub
- GitHub Actions
- GitHub CLI
- README 문서
- ROADMAP 문서
- AGENTS 문서
- JARVIS_RULES 문서
- DEVELOPMENT_WORKFLOW 문서
- Brain 라우팅 테스트
- PromptBuilder 준비
- Jarvis identity / personality / response style 분리
- Sprint 코드네임 정리
- Configuration Layer
- JarvisConfig
- ConfigurationLoader
- ProviderFactory

### Changed

- Brain Routing 구조 개선
- Agent별 키워드 alias 구조 추가
- Memory 우선순위 개선
- Memory 저장 형식을 날짜/시간 포함 형식으로 개선
- Memory 조회 출력을 번호와 블록 형태로 개선
- 자연어 메모 삭제 명령 개선
- GitHub Actions로 자동 검사 흐름 추가
- 버전 관리를 날짜 기준이 아니라 마일스톤 기준으로 변경
- ChatService가 Provider 호출 전에 PromptBuilder를 사용하도록 변경
- Sprint 5 미션을 The First Configuration으로 정리
- Runtime settings를 Configuration Layer에서 읽도록 변경
- `.env` 기반 설정을 이번 Sprint 범위에서 제외

### Fixed

- Memory Routing 버그 수정
- `기억해 VOO 투자`가 Invest가 아니라 Memory로 가도록 수정
- 없는 번호의 메모 삭제 시 예외 메시지 처리
- 자연어 삭제 명령 개선
