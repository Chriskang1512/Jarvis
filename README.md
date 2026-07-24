# Jarvis

Python 기반 개인 AI 비서 프로젝트입니다.

Jarvis는 사용자의 채팅 명령을 받아 Brain이 명령을 분석하고, 작업 성격에 맞는 Agent에게 일을 배정하는 구조로 개발합니다.

## Sprint 18 Agent Core Design

Sprint 18 evolves the existing runtime into a unified Agent Core:

```text
Goal -> Plan -> Validate -> Optimize -> Execute -> Verify -> Journal
```

The approved migration design is documented in:

- [`Agent Core gap analysis`](docs/architecture/agent-core-gap-analysis.md)
- [`Planner contract`](docs/architecture/planner-contract.md)
- [`Plan Validator and Optimizer`](docs/architecture/plan-validator-optimizer.md)
- [`Execution Cost Model`](docs/architecture/execution-cost-model.md)
- [`Task state machine`](docs/architecture/task-state-machine.md)
- [`Checkpoint and resume contract`](docs/architecture/checkpoint-resume-contract.md)
- [`Execution Journal`](docs/architecture/execution-journal.md)
- [`ADR 0024 - Agent Core Integration`](docs/adr/0024-agent-core-integration.md)

Sprint 18.1 now provides the first executable contract layer alongside the
legacy runtime:

- versioned `GoalEnvelope`, `AgentPlan`, `PlanStep`, and `PlanBinding` models;
- fail-closed Registry, dependency, side-effect, verification, and idempotency
  validation;
- an auditable no-op optimizer that rejects semantic fingerprint changes;
- a compatibility adapter from the current `ExecutionPlan`;
- contract version negotiation with explicit multi-version Adapter paths.
- operation-level minimum and recommended contract-version gates.
- capability deprecation and calendar-date sunset lifecycle policies.

Sprint 18.3.1 connects the Task State Machine to the live Runtime path:

- every RuntimeTask projects `PLANNING -> VALIDATING -> OPTIMIZING -> READY`
  before execution without re-running completed Planner work;
- every successful step enters `VERIFYING`;
- Voice confirmation resumes the same task and checkpoint instead of creating
  a replacement task;
- cancellation reaches `CANCELLED` without invoking the confirmed Ability;
- retry and authentication pause behavior consume `RecoveryDecision`;
- every transition publishes a privacy-safe Core EventBus envelope.

## Current Version

v0.6.0 - Sprint 17.6 Google Workspace Integration Polish

## v0.6.0 Sprint 17.6

Sprint 17.6 joins Calendar, Contacts, and Gmail into one confirmation-safe
Workspace flow.

Key points:

- `Contacts -> Gmail` resolves a contact email before composing the message.
- `Calendar -> Gmail` reads the requested event and freezes its title and time
  into the mail preview.
- Cross-Ability steps declare dependencies and exchange provider-independent
  data through the runtime task context.
- Gmail send still stops at `confirm_required`; the previewed recipient,
  subject, and body are not reparsed after confirmation.
- Recent-mail speech stays compact: sender, shortened subject, and time only.
- Opening a specific unread Gmail message marks it read by removing the
  `UNREAD` label; listing mail never changes read state.
- Gmail auth and permission errors explain when OAuth reauthentication is
  required.

Supported examples:

```text
우수 연락처 찾아서 테스트 메일 보내줘
아야에게 내일 오후 3시 일정 메일로 보내줘
최근 메일 알려줘
첫 번째 읽어줘
답장해줘
```

## v0.6.0 Sprint 17.5

Sprint 17.5 completes the Google communication vertical with confirmed Gmail
send and reply support.

Key points:

- Gmail keeps `gmail.readonly` and adds the minimum `gmail.send` scope.
- Compose resolves explicit addresses first, then exact Google Contacts names
  and aliases. Missing, invalid, or ambiguous recipients are blocked.
- A complete provider-independent draft is previewed and stored before
  confirmation. Confirmation sends that exact draft without reparsing.
- Send and reply are always `confirm_required`; cancellation performs no Gmail
  API call.
- Per-action fingerprints block repeated confirmed sends in the runtime.
- Successful API responses are verified by re-reading sent recipient, subject,
  message ID, and thread ID metadata.
- Logs retain only masked recipients, subject hashes, and body lengths.

Supported examples:

```text
아야에게 내일 오후 3시에 만나자고 메일 보내줘
test@example.com으로 테스트 메일 보내줘
그 메일에 확인했다고 답장해줘
```

Configuration and verification details are documented in
[`docs/google-gmail.md`](docs/google-gmail.md).

## v0.6.0 Sprint 17.4

Sprint 17.4 adds a read-only Gmail vertical slice through the existing Google
provider and Ability result contracts.

Key points:

- `JARVIS_MAIL_PROVIDER=google` enables Gmail read access.
- The OAuth helper `scripts/google_gmail_auth.py` adds Gmail read-only scope
  while preserving the existing Calendar and Contacts scopes.
- Supported read commands include recent mail, unread mail, today's mail, and
  sender searches such as GitHub or OpenAI mail.
- Mail lists read sender and subject only by default; send/delete/archive/label
  changes are out of scope.

Configuration details are documented in
[`docs/google-gmail.md`](docs/google-gmail.md).

## v0.6.0 Sprint 17.3

Sprint 17.3 extends Google Contacts from read-only lookup to safe create/update
operations through the existing Contact Ability contract.

Key points:

- `JARVIS_CONTACTS_PROVIDER=google` can use Google People API for contact reads,
  creates, and updates.
- Create and update require confirmation.
- Updates must resolve to Google People API `people/...` resource names before
  writing.
- Ambiguous contacts return clarification instead of updating the first match.
- Delete remains out of scope for this sprint.

Configuration details are documented in
[`docs/google-contacts.md`](docs/google-contacts.md).

## v0.6.0 Sprint 17.2

Sprint 17.2 adds a read-only Google Contacts vertical slice through the existing
Contact Ability contract.

Runtime path:

```text
Voice Session
  |
OpenAI STT
  |
Semantic Transcript Layer
  |
Intent Parser
  |
Planner
  |
RuntimeTask / Dispatcher
  |
Contact Ability
  |
GoogleContactsProvider
  |
Structured ContactResult
  |
Formatter / TTS
```

Example utterances:

```text
우수 연락처 알려줘
아야 전화번호 찾아줘
김민수 이메일 주소 알려줘
```

Configuration details are documented in
[`docs/google-contacts.md`](docs/google-contacts.md).

## v0.6.0 Sprint 17.1

Sprint 17.1 extends Jarvis from Google Calendar read access to verified Google
Calendar create, update, and delete writes through the existing Calendar
Ability provider boundary.

Current voice/runtime path:

```text
Voice Session
  |
OpenAI STT
  |
Semantic Transcript Layer
  |
Intent Parser
  |
Planner
  |
RuntimeTask / Dispatcher
  |
Calendar Ability
  |
CalendarProvider
  |
MockCalendarProvider / GoogleCalendarProvider
  |
Structured CalendarResult
  |
Formatter / TTS
```

Google Calendar support now includes read and write operations. Writes require
confirmation, support Google Calendar reminder overrides, and verify the stored
event by reading it back before reporting success.

Verified manual integration:

- OAuth authentication completed for `lab810108@gmail.com`.
- Today query returned `2026-07-18 20:00 테스트`.
- Next week query returned `2026-07-19 15:00 테스트1`.
- Full regression test suite passes: `624 tests OK (skipped=2)`.

Configuration details are documented in
[`docs/google-calendar.md`](docs/google-calendar.md).

## v0.4.0 Stable Release

v0.4.0 promotes the Release Candidate architecture to stable.

Stable release status:

```text
Planner, Execution Kernel, Result Merge, Voice, Scheduler, and Agent Runtime
are now the stable v0.4.0 architecture.
```

## v0.4.0 Release Candidate

v0.4.0 RC does not add new features. Its goal is to freeze the stable v0.4.0
architecture created from Beta.1 through Beta.7.

Official goal:

```text
v0.4.0 RC freezes Planner, Execution Kernel, Result Merge, Voice, Scheduler,
and Agent Runtime as the stable v0.4.0 architecture.
```

v0.4.0 is the point where Jarvis becomes a small framework:

```text
Planner
  |
Execution Kernel
  |
Scheduler
  |
Agent Runtime
  |
Voice
```

Release Candidate status:

```text
All Beta.1-Beta.7 tests pass.
No new runtime feature is added in RC.
Public APIs remain backward compatible.
Import boundaries remain enforced by tests.
```

## v0.4.0 Release Note Draft

v0.4.0 turns Jarvis from a feature collection into a layered orchestration
framework.

Included Beta milestones:

- Beta.1 Intent Planner
- Beta.2 Execution Graph Runtime
- Beta.3 Capability Context
- Beta.4 Result Merge
- Beta.5 Voice Integration
- Beta.6 Scheduler Foundation
- Beta.7 Agent Runtime

Core architecture:

```text
User
  |
Planner
  |
Execution Graph
  |
Execution Kernel
  |
UnifiedResult
  |
Voice
```

Lifecycle architecture:

```text
Agent Runtime
  |
Scheduler
  |
Execution Kernel
  |
UnifiedResult
```

Excluded from v0.4.0:

- Permission Layer implementation
- Memory Foundation implementation
- new Tool Router implementation
- Plugin System implementation
- real OpenAI voice synthesis
- real audio playback
- persistence layer
- background daemon
- async loop
- OS scheduler

Next candidates for v0.5:

- Permission Layer
- Memory Foundation
- Tool Router
- Plugin System
- first real tool calling
- OpenAI Voice Provider actual implementation
- real audio playback
- persistence layer
- EventBus async fan-out

## v0.4.0 Stable Public APIs

- `ExecutionGraphRunner.run()`
- `ExecutionGraphRunner.run_unified()`
- `ResultMerger.merge()`
- `VoiceService.speak()`
- `Scheduler.schedule()`
- `Scheduler.get()`
- `Scheduler.list()`
- `Scheduler.cancel()`
- `Scheduler.due_tasks()`
- `Scheduler.trigger_due()`
- `AgentRuntime.start()`
- `AgentRuntime.stop()`
- `AgentRuntime.tick()`

## v0.4 Beta.7 - Agent Runtime

Beta.7 introduces the first minimal Agent Runtime layer.

AgentRuntime is not the executor. It is the Runtime Layer that manages the
lifecycle between Scheduler and the Execution Kernel.

Execution Kernel is Jarvis's common execution layer. It includes
ExecutionRunner and ResultMerger. Planner, Scheduler, and AgentRuntime call the
Execution Kernel to perform work. The Kernel returns `UnifiedResult`, the stable
execution interface for downstream layers.

```text
Main pipeline:

User
  |
Planner
  |
Execution Graph
  |
ExecutionRunner
  |
ResultMerge
  |
UnifiedResult
  |
Voice
```

```text
Lifecycle path:

AgentRuntime
  |
Scheduler.due_tasks(now)
  |
Scheduler.trigger_due(now)
  |
ExecutionRunner.run_unified()
  |
UnifiedResult
```

Agent Runtime knows Scheduler and an Execution Kernel interface only.

Agent Runtime does not know Planner.

Agent Runtime does not know Voice.

Agent Runtime does not know Capabilities.

Beta.7 supports manual ticks only:

```text
start()
  |
tick(now)
  |
due_tasks(now)
  |
trigger_due(now)
  |
IDLE
```

Beta.7 does not start a background loop, thread, asyncio loop, daemon, planner
loop, autonomous memory loop, or automatic voice playback.

Agent Runtime Philosophy:

```text
AgentRuntime coordinates lifecycle.
AgentRuntime is not the executor.
Execution Kernel executes.
Scheduler owns schedule lifecycle.
UnifiedResult remains the execution outcome.
```

Current core architecture:

```text
                User
                  |
                  v
             Planner
                  |
                  v
          Execution Graph
                  |
                  v
        Execution Kernel
        (Runner + Merge)
          |        |
          |        v
          |   UnifiedResult
          |        |
          |      Voice
          |
          v
      Scheduler
          ^
          |
    Agent Runtime
```

## v0.4 Beta.6 - Scheduler Foundation

Beta.6 introduces the Scheduler Foundation.

Beta.6의 목표는 시간을 흐르게 만드는 것이 아니라, 예약 Task의 Lifecycle을
모델링하는 것이다.

Beta.6 does not run background threads, asyncio loops, cron parsers, OS
schedulers, Windows Scheduler, background daemons, real notifications, or
automatic voice playback.

```text
ScheduleRequest
  |
Schedule
  |
ScheduledTask
  |
TaskState
  |
SchedulerService / Scheduler
  |
due_tasks(now)
  |
ExecutionRunner.run_unified()
  |
UnifiedResult
```

Supported schedule type:

```text
one-shot run_at datetime only
```

Task lifecycle:

```text
PENDING
READY
RUNNING
COMPLETED
FAILED
CANCELLED
```

Scheduler Foundation Philosophy:

```text
Scheduler models task lifecycle.
Scheduler does not make time flow.
Scheduler does not know Planner.
Scheduler does not know Voice.
Scheduler does not know Capabilities.
Scheduler runs work only through ExecutionRunner.run_unified().
Scheduler receives UnifiedResult.
```

Beta.6 manual trigger flow:

```text
ScheduleRequest
  |
InMemoryScheduler.schedule()
  |
ScheduledTask
  |
trigger_due(now)
  |
RUNNING
  |
ExecutionRunner.run_unified()
  |
COMPLETED or FAILED
```

## v0.4 Beta.5 - Voice Integration

Beta.5 introduces the Voice Integration layer. Jarvis does not play audio yet;
this sprint converts a `UnifiedResult` into a provider-generated `VoiceResult`.

```text
Planner
  |
Execution
  |
Merge
  |
UnifiedResult
  |
VoiceService
  |
VoiceProvider
  |
VoiceResult
```

Voice knows only `UnifiedResult`.

Voice does not know Planner.

Voice does not know Execution Graph.

Voice does not know Capabilities.

Voice result contract:

```json
{
  "text": "3 capabilities completed",
  "audio": null,
  "provider": "mock",
  "duration_ms": 0,
  "metadata": {}
}
```

Beta.5 scope:

```text
UnifiedResult
  |
VoiceService
  |
VoiceResult
```

Audio playback through speakers remains future work.

Voice Integration Philosophy:

```text
Voice receives UnifiedResult only.
Voice reads summary only.
Voice delegates synthesis to a provider.
Voice does not play audio in Beta.5.
Providers are replaceable through DI.
```

Beta.5 completion status: implemented with MockVoiceProvider and provider
placeholder for future OpenAI voice synthesis.

## v0.4 Beta.4 - Result Merge

Beta.4 introduces the Result Merge layer. Execution Graph still runs
capabilities and returns ordered node results, but consumers can now ask for one
merged `UnifiedResult` response.

Status: Complete. Beta.4 is approved for closure and Jarvis can enter Beta.5
Voice Integration.

```text
Planner
  |
Execution Graph
  |
Capabilities
  |
Result Merge
  |
UnifiedResult
```

Unified result contract:

```json
{
  "summary": "3 capabilities completed",
  "results": [],
  "warnings": [],
  "errors": [],
  "metadata": {}
}
```

Merge rules:

```text
success/completed -> results
warning -> warnings
failed/error -> errors
```

Metadata preserves execution details such as `execution_id`, `plan_id`, node
count, elapsed time, completed node count, timestamp, and per-node timing.

`UnifiedResult` is immutable after merge. `ResultMerger` receives execution
results as input and returns a separate `UnifiedResult`; it is not stored inside
`ExecutionRunResult`.

Result Merge Philosophy:

```text
Merge receives results only.
Merge never plans.
Merge never executes tools.
Merge never reads Memory.
Merge never calls capabilities.
Merge returns one UnifiedResult for Voice and UI.
```

`ExecutionGraphRunner.run()` remains the raw execution contract.
`ExecutionGraphRunner.run_unified()` executes and merges through the configured
`ResultMerger`.

Beta.5 Voice Integration entry conditions:

```text
UnifiedResult.summary is stable for Voice output.
UnifiedResult.results, warnings, errors, and metadata are stable for UI output.
Result order follows plan execution order.
Partial results are preserved when one node fails.
Summary reports warning/error counts without embedding detailed issue text.
Diagnostics metadata includes execution, plan, node, status, timing, and counts.
```

## v0.4 Beta.3 - Capability Context

Beta.3 introduces Execution Context: temporary data that exists only during one
execution run. It is not Memory.

```text
Finance
  |
Execution Context
  |
Japanese
  |
Execution Context
  |
Creator
```

Context contract:

```json
{
  "context_version": "1.0",
  "execution_id": "exec_xxx",
  "values": {
    "finance_001": {
      "result": {}
    }
  }
}
```

Tool input contract:

```json
{
  "user_input": "",
  "previous_results": [],
  "execution_snapshot": {}
}
```

`ExecutionInputData` is append-only. Existing fields remain backward compatible,
and capabilities should ignore unknown fields.

Execution order:

```text
Execute
  |
Result
  |
Context Update
  |
Next Node
```

Execution Context Philosophy:

```text
Execution Context is temporary.
Execution Context belongs to the Runner.
Capabilities never own execution context.
Capabilities receive immutable execution snapshots.
Capabilities never mutate execution context.
Runner is the only owner of execution state.
Execution Context is destroyed after execution.
Memory remains long-term storage.
```

## v0.4 Beta.2 - Execution Graph Runtime

Beta.2 introduces the Execution Layer. Planner still never executes. Runner
walks a validated graph sequentially and delegates routing, authorization, and
tool execution.

```text
User
  |
Brain
  |
Intent Planner
  |
Plan Validator
  |
Execution Graph Runner
  |
Capability Router
  |
Permission
  |
Dispatcher
  |
Tool Result
```

Runner result contract:

```json
{
  "execution_id": "exec_xxx",
  "plan_id": "plan_xxx",
  "status": "completed",
  "results": [
    {
      "node_id": "life_001",
      "status": "completed",
      "result": {},
      "started_at": "",
      "finished_at": ""
    }
  ]
}
```

Execution Runner Philosophy:

```text
Runner executes.
Runner never plans.
Runner never validates.
Runner never selects capabilities.
Runner never selects tools.
Runner delegates routing.
Runner delegates authorization.
Runner delegates execution.
```

## v0.4 Beta.1 - Intent Planner Contract

Beta begins Capability Orchestration. Beta.1 does not execute multi-tool plans;
it defines the stable planning contract that future execution can safely use.

```text
User
  |
Brain
  |
Intent Planner
  |
Capability Plan
  |
Plan Validator
  |
Capability Router
  |
Tool
  |
Permission
  |
Dispatcher
```

Detailed planning boundary:

```text
Brain
  |
Intent Planner
  |
Capability
  |
Intent
  |
Capability Router
  |
Tool
```

Planner output is capability-level only:

```json
{
  "capability": "finance",
  "intent": "compound simulation"
}
```

Planner output must not name tools.

Planning contract:

```json
{
  "plan_id": "plan_xxx",
  "planner_version": "0.1",
  "graph_version": "1.0",
  "goal": "",
  "status": "CREATED",
  "requires_planning": true,
  "permission_mode": "SAFE",
  "execution_mode": "sequential",
  "graph": {
    "nodes": [
      {
        "id": "finance_001",
        "step": 1,
        "capability": "finance",
        "intent": "compound simulation",
        "input": "VOO를 20년 적립",
        "status": "CREATED",
        "required": true,
        "confidence": 0.82
      }
    ],
    "edges": [
      {
        "id": "edge_001",
        "from": "finance_001",
        "to": "jp_002",
        "type": "sequential"
      }
    ],
    "metadata": {}
  }
}
```

Planner Philosophy:

```text
Brain decides if planning is required.
Planner decomposes goals.
Planner knows capabilities.
Capabilities own their tools.
Permission authorizes.
Dispatcher executes.
Merge returns one response.
```

Planner Design Rules:

```text
1. Planner never knows tools.
2. Planner plans at capability level.
3. Planner never touches Memory.
4. Planner never touches Dispatcher.
5. Planner never bypasses Permission.
6. Planner outputs executable capability tasks only.
7. Planner produces a stable planning contract.
8. Execution remains sequential in Beta.1.
```

## v0.4 Sprint 7 - Life Capability Alpha

Life is the fifth real capability application. It is intentionally closer to
Memory than the previous capability apps, but it still plugs into the same
Capability -> ToolRegistry -> BrainToolRouter -> Permission -> Dispatcher path.

```text
Life Capability
  |
  |-- life_todo
  |-- life_reminder
  |-- life_routine
  |-- life_habit
  `-- life_reflection
       |
Memory-aware when available
       |
ToolMetadata
       |
Brain Tool Router
       |
Permission
       |
Dispatcher
```

Included SAFE tools:

- `life_todo`: turns loose notes into prioritized todo lists.
- `life_reminder`: prepares Scheduler-ready reminder payloads without creating
  real reservations.
- `life_routine`: drafts morning, evening, study, workout, or project routines.
- `life_habit`: creates simple habit tracking templates.
- `life_reflection`: summarizes a day or sprint into summary, wins, problems,
  ideas, and next actions.

Reminder outputs are ready for a future Scheduler:

```json
{
  "message": "...",
  "recommended_time": "tomorrow morning",
  "priority": "normal",
  "ready_for_scheduler": true
}
```

Life may read Memory through approved Memory interfaces, but Memory remains Core.
Life does not own Memory.

## Capability Philosophy

```text
Brain decides.
Capability specializes.
Tool executes.
Memory remembers.
Permission protects.
Dispatcher delivers.
```

## v0.4 Sprint 6 - Hotel Capability Alpha

Hotel is the fourth real capability application and Jarvis's hospitality
operations assistant for front office and rooms division workflows.

```text
Hotel Capability
  |
  |-- hotel_schedule_planner
  |-- hotel_complaint_report
  `-- hotel_complaint_manual
       |
ToolMetadata
       |
Brain Tool Router
       |
Permission
       |
Dispatcher
```

Included SAFE tools:

- `hotel_schedule_planner`: drafts editable staff schedules and returns
  conflicts, unresolved constraints, and manager notes.
- `hotel_complaint_report`: creates structured manager-style complaint reports.
- `hotel_complaint_manual`: creates SOP guidance for complaint scenarios such as
  noise, refund requests, cleanliness, and difficult guest interactions.

Hotel follows the same small-app capability structure:

```text
jarvis/capabilities/hotel/
  __init__.py
  metadata.py
  tools/
    schedule_planner.py
    complaint_report.py
    complaint_manual.py
  prompts/
    schedule/
    complaint_report/
    complaint_manual/
  tests/
```

Schedule planning is intentionally alpha-grade: Jarvis creates a draft and
surfaces conflicts instead of pretending to be a perfect optimizer.

## v0.4 Sprint 5 - Creator Capability Alpha

Creator is the third real capability application. It is a creative engine, not a
YouTube-only utility.

```text
Creator Capability
  |
  |-- creator_lyrics
  |-- creator_music_prompt
  |-- creator_title
  |-- creator_description
  `-- creator_song_package
       |
ToolMetadata
       |
Brain Tool Router
       |
Permission
       |
Dispatcher
```

Included SAFE tools:

- `creator_lyrics`: generate structured song lyrics.
- `creator_music_prompt`: generate prompts for Suno, Udio, and Stable Audio style tools.
- `creator_title`: generate ten title candidates.
- `creator_description`: generate YouTube or song descriptions.
- `creator_song_package`: local Creator-only orchestration demo that returns lyrics,
  music prompt, titles, thumbnail prompt, description, and tags.

Creator treats prompts as first-class assets:

```text
jarvis/capabilities/creator/
  __init__.py
  metadata.py
  song/
  video/
  blog/
  presentation/
  tools/
    lyrics.py
    music_prompt.py
    title.py
    description.py
    song_package.py
  prompts/
    lyrics/
    music/
    thumbnail/
    script/
  tests/
```

Creator is designed around sub-domains. Song is the first implemented
sub-domain, but Video, Blog, and Presentation are reserved as future creative
domains.

Creator output contracts include project and asset identity:

```json
{
  "project": "jarvis_theme_song",
  "subdomain": "song",
  "asset": "lyrics"
}
```

`creator_song_package` is not the Multi Tool Planner. It only demonstrates local
sequential execution inside Creator. Cross-capability orchestration belongs to
v0.4 beta.

## v0.4 Sprint 4 - Finance Capability Alpha

Finance is the second real capability application. It proves that a different
domain can be added through the same Capability -> Tool -> Permission ->
Dispatcher path without changing Brain.

```text
Finance Capability
  |
  |-- finance_compound
  |-- finance_average_price
  |-- finance_profit
  |-- finance_portfolio
  `-- finance_exchange
       |
ToolMetadata
       |
Brain Tool Router
       |
Permission
       |
Dispatcher
```

Included SAFE tools:

- `finance_compound`: local compound interest simulation.
- `finance_average_price`: weighted average purchase price for buy lots.
- `finance_profit`: profit/loss, return rate, and after-tax result.
- `finance_portfolio`: simple allocation and diversification summary.
- `finance_exchange`: KRW, USD, and JPY conversion using supplied or sample rates.

Finance follows the same small-app capability structure:

```text
jarvis/capabilities/finance/
  __init__.py
  metadata.py
  tools/
    average_price.py
    compound.py
    exchange.py
    portfolio.py
    profit.py
  prompts/
  tests/
```

Capability metadata includes `version`, `status`, and `owner` so each
capability can mature and release independently.

The v0.4 Alpha Architecture Review is documented in
`docs/architecture/alpha-review-v0.4.md`.

## v0.4 Sprint 3 - Japanese Capability Alpha

Japanese is the first real capability built on top of the Capability Plugin
Framework. Brain remains unchanged: Japanese tools are discovered through the
Japanese capability, registered into ToolRegistry, authorized by PermissionLayer,
and executed by ToolDispatcher.

```text
Japanese Capability
  |
  |-- japanese_translate
  |-- japanese_grammar
  |-- japanese_reply
  `-- japanese_review
       |
ToolMetadata
       |
Brain Tool Router
       |
Permission
       |
Dispatcher
```

Included SAFE tools:

- `japanese_translate`: simple Korean/Japanese learning translations with
  hiragana spacing, standard Japanese, Korean pronunciation, and Korean meaning.
- `japanese_grammar`: simple grammar differences such as `しらない vs わからない`.
- `japanese_reply`: casual Japanese reply drafts for preferred names such as
  `アヤ` and `ユイ`.
- `japanese_review`: recent Japanese expressions from memory when available,
  with fallback guidance when memory is empty.

Japanese capability is structured as a small app:

```text
jarvis/capabilities/japanese/
  __init__.py
  metadata.py
  tools/
    translate.py
    grammar.py
    reply.py
    review.py
  prompts/
    translate.md
    grammar.md
    reply.md
  tests/
```

Tool metadata also carries `examples` so future Brain routing can combine
`supported_intents` and examples for better intent matching.

## v0.4 Sprint 2 - Capability Plugin Framework

Capabilities are now the primary extension unit for Jarvis.

```text
Brain
  |
Brain Tool Router
  |
Tool Registry
  ^
  |
Capability Registry
  |
  |------|----------|-------|---------|------|
Finance Japanese   Hotel   Creator   Life
  |
Tool Collection
```

The capability layer sits above the existing Tool Registry. Each capability owns
its tools, each tool owns its metadata, the Permission Layer authorizes, and the
Dispatcher executes.

```text
Capability
  |
Tool
  |
Permission
  |
Dispatcher
```

Sprint 2 includes framework and skeletons only. Finance, Japanese, Hotel,
Creator, and Life business logic will be added in later sprints.

## v0.4 Phase 1 - Brain Tool Router

Jarvis now checks safe tool routes before sending normal chat to the LLM.

```text
User
  |
Voice / Text
  |
Brain
  |
Brain Tool Router
  |
  |--------------------|
  |                    |
Tool Route            LLM Route
  |                    |
Permission            ChatCommand
  |                    |
Dispatcher            ChatService
  |
Tool
```

The Brain Tool Router is registry-driven. It reads `ToolMetadata` from the
existing `ToolRegistry`, scores candidate tools from metadata such as
`capability`, `aliases`, `supported_intents`, `input_mode`, and
`input_prefixes`, checks the existing `PermissionLayer`, and then returns a
`ToolRequest` for the `ToolDispatcher`.

The Brain decides. The Permission Layer authorizes. The Dispatcher executes.
The Registry describes available tools.

Only SAFE tools are eligible for automatic routing in v0.4 Phase 1. Ambiguous
requests continue to the normal LLM conversation path.

Jarvis는 날짜가 아니라 프로젝트 완성 단계, 즉 마일스톤 기준으로 버전을 관리합니다.

## 현재 상태

현재 Jarvis는 로컬 CLI 채팅 버전입니다.

완료된 핵심 내용:

- Python 프로젝트 구조 구축
- Brain 라우팅 구조 구축
- Agent 기본 구조 구축
- Memory Agent 기본 기능 구축
- Scheduler Stub 추가
- Git / GitHub 연동
- GitHub Actions(CI) 구축
- GitHub CLI(`gh`)로 CI 확인 가능

현재 Mock Provider, OpenAI Provider, Claude Provider가 공존합니다. 기본값은 안전하게 `mock`입니다.

## 버전 관리 규칙

Jarvis의 버전은 기능이 완성되는 단계에 따라 올라갑니다.

```text
v0.1.0 = Project Bootstrap
v0.2.0 = First Functional AI
v0.3.0 = External Services
v0.5.0 = Automation
v1.0.0 = Personal AI Assistant
```

새로운 기능이 완성될 때마다 버전을 올리고, 변경 내용은 `CHANGELOG.md`에 기록합니다.

## Sprint Codenames

Jarvis는 Sprint마다 코드네임을 사용합니다.

```text
Sprint 1  - The First Heartbeat
Sprint 2  - The First Command
Sprint 3  - The First Conversation
Sprint 4  - The First Personality
Sprint 5  - The First Configuration
Sprint 6  - The First Breath
Sprint 7  - The First Memory
Sprint 8  - The Second Brain
Sprint 9  - The First Voice
Sprint 10 - The First Face
```

## Beta Roadmap

Jarvis v0.2.0 beta는 아래 순서로 진행합니다.

```text
v0.2.0-beta.1 - Voice Pipeline Foundation
v0.2.0-beta.2 - Metadata Console
v0.2.0-beta.3 - Tool Calling
```

v0.2.0-beta.2의 목표는 `Metadata Console`입니다.

Diagnostics는 UI가 아니라 개발자 진단 도구입니다.

```text
Modules publish metadata
  |
DiagnosticsCollector
  |
DiagnosticsConsole
```

진단 콘솔은 별도 진입점으로 실행합니다.

```powershell
python diagnostics_main.py
```

Diagnostics Console은 아래 정보를 표시합니다.

```text
Session
Provider
Performance
Pipeline Status
Health
Event Log
```

Console은 metadata를 렌더링만 합니다. Source of truth는 `DiagnosticsCollector`입니다.

DiagnosticSnapshot은 호환성을 위해 `version` 필드를 가집니다. Beta.2의 snapshot version은 `1`입니다. 향후 Finance, Memory, Calendar, Automation metadata가 추가되면 snapshot version을 올려 CLI, GUI, REST API가 같은 계약을 공유할 수 있게 합니다.

v0.3.0-beta.1의 목표는 `Voice Experience`입니다.

이번 Sprint의 목표는 완성형 음성비서가 아니라 사람처럼 대화하는 음성 경험의 기반입니다.

```text
VoiceSession
  |
VoicePipeline
  |
Streaming-ready TTS
  |
DiagnosticsCollector
```

Voice Experience 기준:

```text
[x] Voice Session 관리
[x] Streaming-ready TTS 계약
[x] TTS chunk output
[x] 응답 지연 측정
[x] 향후 Interrupt 지원 구조
[x] Diagnostics event publish
```

v0.3 기능은 아래 질문을 통과해야 합니다.

```text
확장 가능한가?
Provider를 교체할 수 있는가?
Permission Layer와 자연스럽게 연결되는가?
Diagnostics로 추적 가능한가?
Snapshot으로 재현 가능한가?
```

v0.2.0-beta.1의 목표는 `Voice Pipeline Foundation`입니다.

```text
Wake Word
  |
Speech-to-Text
  |
ChatService
  |
ChatProvider
  |
Text-to-Speech
```

기존 CLI는 그대로 유지합니다.

```powershell
python main.py
```

음성 파이프라인은 별도 진입점으로 실행합니다.

```powershell
python voice_main.py
```

Voice 설정은 환경변수로 관리합니다.

```powershell
$env:JARVIS_WAKE_WORD="hey jarvis"
$env:JARVIS_STT_PROVIDER="console"
$env:JARVIS_TTS_PROVIDER="pyttsx3"
$env:JARVIS_VOICE_DEBUG="true"
$env:JARVIS_VOICE_ONCE="true"
```

실험용 마이크/TTS Provider:

```powershell
$env:JARVIS_STT_PROVIDER="microphone"
$env:JARVIS_TTS_PROVIDER="pyttsx3"
```

Default TTS provider:

```text
pyttsx3
```

Jarvis defaults to `pyttsx3` for local voice output. The VoicePipeline still only depends on the TTS Provider contract, so future providers such as Piper, OpenAI, Azure, or ElevenLabs can replace it without changing the pipeline.

Local TTS provider test:

```powershell
$env:JARVIS_TTS_PROVIDER="piper"
$env:JARVIS_TTS_PIPER_PATH="piper"
$env:JARVIS_TTS_MODEL_PATH="C:\path\to\voice.onnx"
$env:JARVIS_TTS_STREAMING="true"
python voice_main.py
```

`config.json` can also select the TTS provider:

```json
{
  "tts": {
    "provider": "pyttsx3",
    "voice": "default",
    "streaming": true
  }
}
```

Piper can be selected as an interchangeable local provider:

```json
{
  "tts": {
    "provider": "piper",
    "voice": "default",
    "streaming": true,
    "piper_path": "piper",
    "model_path": "C:\\path\\to\\voice.onnx"
  }
}
```

Supported TTS provider names:

```text
console
pyttsx3
piper
```

Piper is optional. If Piper or the voice model is missing, Jarvis keeps the TTS provider contract and falls back to console output while publishing `voice.tts.error`.

## Sprint 3.2 - Memory Begins

Mission 3.2 adds short-term conversational memory for the current session.

```text
VoiceSession
  |
ConversationContext
  |
History Buffer
  |
PromptBuilder
  |
ChatProvider
```

Jarvis now keeps recent user and assistant turns, injects that history into the next prompt, and trims the buffer by configured turn and token windows. The active `VoiceSession` owns the `ConversationContext`; no global conversation state is used.

This is not long-term memory. User profiles, vector databases, persistent storage, tool calling, and permission layers stay out of scope for this mission.

Conversation diagnostics events:

```text
conversation.started
conversation.updated
conversation.context.injected
conversation.finished
```

## Sprint 3.3 - First Action

Mission 3.3 adds the first Tool Calling framework. Jarvis can now execute safe actions through a registry and dispatcher.

```text
Voice Session
  |
Conversation Context
  |
Prompt Builder
  |
LLM
  |
Tool Dispatcher
  |
Tool Registry
  |
Safe Tool
```

Built-in safe tools:

```text
time
calculator
diagnostics
memory_read
```

Tool domains:

```text
core
memory
creator
japanese
finance
golf
hotel
life
ai
plugins
```

Mission 3.3 only marks tools with domain metadata and exposes domain lookup through ToolRegistry. Future domain tools can be added by creating a new tool and registering it, without changing ToolDispatcher or core pipeline code.

CLI examples:

```powershell
tool list
tool domains
tool domain core
tool time
tool calculator 2 + 3 * 4
tool diagnostics
tool memory_read user_name
```

Tool lifecycle diagnostics events:

```text
tool.requested
tool.selected
tool.started
tool.completed
tool.failed
```

Jarvis does not execute actions inside the LLM provider. A provider may request an action later, but ToolDispatcher performs execution through ToolRegistry. This keeps Mission 3.4 Permission Layer ready to intercept tool execution without changing tool implementations.

## Sprint 3.4 - Guardian

Mission 3.4 adds the Permission Layer. Tool execution now passes through a single metadata-driven checkpoint before `Tool.execute()`.

```text
LLM
  |
Tool Dispatcher
  |
Permission Layer
  |
Tool Registry
  |
Tool
```

Permission levels:

```text
safe
confirm
restricted
```

Permission decision statuses:

```text
allowed
confirm_required
denied
```

Permission diagnostics events:

```text
permission.check.started
permission.allowed
permission.confirm.required
permission.denied
permission.failed
```

This mission does not implement confirmation UI, voice confirmation, authentication, account systems, network permissions, or plugin signatures. It only creates the security checkpoint that future tools and Permission Layer policies can use.

## Sprint 3.5 - Long Memory

Mission 3.5 adds a long-term Memory Store. ConversationContext still remembers only the active session; Memory Store remembers across sessions.

```text
VoiceSession
  |
ConversationContext
  |
MemoryManager
  |
MemoryStore
```

Memory categories:

```text
preference
fact
goal
project
routine
```

Memory metadata:

```text
id
category
title
created_at
updated_at
source
tags
```

Retrieval APIs:

```text
find_by_category()
find_by_tag()
find_recent()
search()
```

Default Memory Store config:

```json
{
  "memory_store": {
    "path": "data/memory_store.json"
  }
}
```

This mission does not implement embeddings, vector search, semantic retrieval, AI memory extraction, user profile inference, or cloud sync. It only creates the library where durable memories can live.

## Sprint 3.6 - Expansion

Mission 3.6 adds the local Plugin System foundation. Jarvis can now load builtin plugins and register plugin tools without changing core tool execution.

```text
Plugin
  |
Tool
  |
ToolRegistry
  |
PermissionLayer
  |
ToolDispatcher
```

Plugin metadata:

```text
id
name
version
domain
description
author
enabled
permission_level
```

Plugin registry APIs:

```text
list_plugins()
get_plugin(id)
list_by_domain(domain)
list_enabled()
```

Builtin validation plugin:

```text
builtin.echo
  |
plugin_echo
```

This mission does not implement YouTube, Japanese, Finance, marketplace, remote installs, auto-update, signing, or external credentials. It only creates the local socket where future plugin capabilities can attach.

## Sprint 3.7 - LLM Abstraction

Mission 3.7 adds the provider-independent LLM layer. ChatService now depends on the LLM Provider contract instead of a concrete vendor implementation.

```text
Voice
  |
Conversation
  |
ChatService
  |
LLM Provider
```

LLM provider contract:

```text
generate()
generate_stream()
metadata()
```

Provider metadata:

```text
id
name
model
supports_stream
supports_tools
supports_images
supports_reasoning
```

Implemented providers:

```text
mock
openai
```

The existing Claude adapter remains available through the legacy provider path for compatibility, but new provider work should target `jarvis.llm`.

LLM diagnostics events:

```text
llm.provider.selected
llm.request.started
llm.request.finished
llm.provider.failed
```

Changing the AI provider should now be a configuration change, not a ChatService rewrite.

현재 음성 파이프라인은 foundation 단계입니다. 완벽한 음성비서가 아니라 `Hey Jarvis -> listen -> transcribe -> LLM response -> speak -> log` 흐름을 검증합니다.

Beta 1 Done Criteria:

```text
[x] Wake Word가 동작한다.
[x] 마이크 입력을 받을 수 있다.
[x] STT 결과를 텍스트로 얻는다.
[x] LLM 응답을 생성한다.
[x] TTS로 응답을 읽는다.
[x] 각 단계 로그가 출력된다.
[x] 기존 main.py CLI는 정상 동작한다.
```

## Core Design Principle

Jarvis는 event-driven architecture를 따릅니다.

Core는 누가 이벤트를 소비하는지 알지 않습니다.

## Architecture Law #001

Core는 Vendor를 알지 않습니다.

```text
Core must not know OpenAI, Claude, Gemini, Anthropic, or any vendor name.
Only ProviderFactory may know which vendor provider is selected.
```

향후 Console, Rive, Electron, Unity 같은 renderer뿐만 아니라 Agent, Memory system, Automation module, external integration도 EventBus를 독립적으로 구독합니다.

이 구조는 Jarvis Core와 UI, 자동화, 외부 연동을 느슨하게 연결합니다. 그래서 프로젝트가 커져도 Core 코드를 크게 뜯지 않고 기능을 확장할 수 있습니다.

v0.2.0 Sprint 1의 목표는 첫 심장박동입니다.

```text
Jarvis Core
  |
EventBus
  |
Console Adapter
  |
Status 출력
```

Core는 `JarvisEvent`와 `JarvisState`만 발행합니다. Console, Rive, Electron, Unity 같은 표현 계층은 EventBus를 구독해서 상태를 표시합니다.

v0.2.0 Sprint 2의 목표는 첫 명령 시스템입니다.

```text
Dispatcher routes. Command executes. EventBus broadcasts. Adapters render.
```

```text
Input
  |
Command Dispatcher
  |
Command Registry
  |
Command
  |
EventBus
  |
Console Adapter
```

현재 기본 Command:

- `chat`
- `help`
- `status`
- `version`
- `exit`

등록되지 않은 일반 입력은 `ChatCommand`로 fallback 됩니다.

```text
안녕
오늘 뭐해?
```

위 입력은 `chat 안녕`, `chat 오늘 뭐해?`처럼 대화 명령으로 처리됩니다.

v0.2.0 Sprint 4의 목표는 `The First Personality`입니다.

```text
ChatCommand
  |
ChatService
  |
PromptBuilder
  |
ChatProvider
```

PromptBuilder는 Jarvis identity, personality, response style, special modes를 Provider 밖에서 관리합니다. 그래서 OpenAI, Claude, local provider가 나중에 추가되어도 같은 Jarvis 성격을 공유할 수 있습니다.

Provider는 응답을 생성하지만, Jarvis가 누구인지 정의하지 않습니다. Jarvis의 identity, core rules, personality, special modes는 PromptBuilder가 관리합니다.

현재 Special Modes:

- Project Mode
- Developer Mode
- Japanese Mode
- Hotel Mode
- Finance Mode

v0.2.0 Sprint 5의 목표는 `The First Configuration`입니다.

```text
Jarvis Runtime
  |
Configuration Layer
  |
JarvisConfig
  |
ProviderFactory
  |
ChatProvider
```

Jarvis Core는 Provider 선택, Model 이름, Debug 옵션을 직접 알지 않습니다. 모든 실행 설정은 Configuration Layer에서 공급합니다.

v0.2.0 Sprint 6의 목표는 `The First Breath`입니다.

```text
JarvisConfig
  |
ProviderFactory
  |
MockChatProvider / OpenAIProvider
  |
ChatProvider Interface
  |
ChatService
```

ProviderFactory는 어떤 Provider를 만들지 알지만, `ChatCommand`, `ChatService`, `PromptBuilder`는 어떤 Provider가 사용되는지 모릅니다.

이번 Sprint부터 OpenAI API Key는 `.env`에서만 읽습니다. `config.json`에는 API Key를 절대 넣지 않습니다.

v0.2.0 Sprint 7의 목표는 `The First Memory`입니다.

```text
MemoryService
  |
MemoryProvider
  |
MockMemoryProvider
```

이번 Sprint의 Memory는 아직 오래 저장하지 않습니다. 먼저 `MemoryService -> MemoryProvider` 구조를 만들고, 나중에 SQLite, JSON, Vector DB Provider로 교체할 수 있게 준비합니다.

MemoryService는 현재 ChatService에서 사용되지만, 향후 독립 Domain Service로 확장될 예정입니다.

v0.2.0 Sprint 8의 목표는 `The Second Brain`입니다.

```text
ProviderFactory
  |
MockChatProvider / OpenAIProvider / ClaudeProvider
  |
ChatProvider Interface
  |
ChatService
```

ProviderFactory만 Provider 이름을 알고, Core는 `mock`, `openai`, `claude` 중 무엇이 선택되었는지 알지 않습니다.

## Project Layers

Jarvis는 역할별 Layer를 나누어 확장합니다.

```text
Application Layer
|
|-- Voice
|-- Agents
|-- Memory
`-- Automation

Core Layer
|
|-- Jarvis Core
|-- Event Bus
`-- State Model

Presentation Layer
|
|-- Console
|-- Rive
|-- Electron
`-- Unity

Infrastructure
|
|-- OpenAI
|-- Claude
|-- MCP
|-- Database
`-- Logging
```

## North Star Architecture

Jarvis의 장기 목표 구조입니다.

```text
USER
  |
Input Layer
Keyboard / Voice / API
  |
Intent Router
Dispatcher + Registry
  |
  |--------------------|
  |                    |
Conversation          Commands
  |                    |
ChatService           Calendar / Mail / Stock
  |                    |
PromptBuilder         Tool Services
  |
ChatProvider
  |
OpenAI / Claude / Ollama
  |
EventBus
  |
Console / Electron / Rive
```

현재 구현된 부분:

```text
Input Layer      -> CLI
Intent Router    -> CommandDispatcher + CommandRegistry
Conversation     -> ChatCommand
Brain Tool Router -> Registry metadata driven SAFE tool routing
ChatService      -> ChatService
PromptBuilder    -> PromptBuilder
ChatProvider     -> MockChatProvider / OpenAIProvider / ClaudeProvider
Memory           -> MemoryService + MockMemoryProvider
EventBus         -> EventBus
Console          -> ConsoleEventAdapter
```

아직 예정인 부분:

```text
Voice / API input
Calendar / Mail / Stock Tool Services
OllamaProvider
Electron UI
Rive Visual UI
```

## Design Goals

- UI-independent Core
- Event-driven architecture
- Provider-agnostic AI layer
- Modular Agent system
- Extensible Adapter architecture
- Testability first
- Future-ready (Rive / Electron / Unity)

## 개발 환경

현재 개발 환경은 아래 도구를 기준으로 합니다.

- Python: Jarvis 실행 언어
- VS Code: 코드 편집과 터미널 실행
- Git: 로컬 변경사항 기록
- GitHub: 원격 저장소
- GitHub Actions: push 후 자동 검사
- GitHub CLI(`gh`): 터미널에서 Actions 상태 확인
- Codex: 코드 작성, 구조 개선, 테스트 보조

## Configuration

Jarvis는 `config.json`이 있으면 읽고, 없으면 안전한 기본값을 사용합니다.

현재 기본값:

```text
provider=mock
model=mock
temperature=0.7
debug=false
profile=jarvis
version=v0.3.0-beta.7
```

Bootstrap Flow:

```text
main.py
  |
ConfigurationLoader
  |
JarvisConfig
  |
ProviderFactory
  |
MockChatProvider
  |
ChatService
  |
PromptBuilder
  |
Conversation
```

주의:

```text
API Key는 config.json에 넣지 않습니다.
.env는 GitHub에 올리지 않습니다.
```

OpenAI 사용 예시:

```json
{
  "provider": "openai",
  "model": "gpt-5.5",
  "temperature": 0.7,
  "debug": false,
  "profile": "jarvis",
  "version": "v0.3.0-beta.7"
}
```

Claude 사용 예시:

```json
{
  "provider": "claude",
  "model": "claude-opus-4-6",
  "temperature": 0.7,
  "debug": false,
  "profile": "jarvis",
  "version": "v0.3.0-beta.7"
}
```

`.env` 예시:

```text
OPENAI_API_KEY=여기에_본인_API_Key_입력
ANTHROPIC_API_KEY=여기에_본인_Anthropic_API_Key_입력
```

설치:

```powershell
pip install -r requirements.txt
```

## 현재 프로젝트 구조

```text
.
|-- main.py
|-- README.md
|-- ROADMAP.md
|-- AGENTS.md
|-- JARVIS_RULES.md
|-- DEVELOPMENT_WORKFLOW.md
|-- requirements.txt
|-- config
|   `-- settings.py
|-- docs
|   `-- overview.md
|-- tests
|   `-- test_brain_routing.py
|-- jarvis
|   |-- __init__.py
|   |-- assistant.py
|   |-- agents
|   |   |-- __init__.py
|   |   |-- invest.py
|   |   |-- japanese_shorts.py
|   |   |-- memory.py
|   |   |-- music_youtube.py
|   |   `-- scheduler.py
|   |-- brain
|   |   |-- __init__.py
|   |   `-- controller.py
|   |-- memory
|   |   |-- __init__.py
|   |   `-- store.py
|   |-- models
|   |   `-- __init__.py
|   `-- utils
|       `-- __init__.py
`-- logs
    `-- .gitkeep
```

## Brain / Agent / Memory 구조

`main.py`는 사용자 입력을 받고 Brain에게 전달합니다.

`jarvis/brain/controller.py`는 명령을 분석하고 어떤 Agent가 처리할지 결정합니다.

현재 라우팅 우선순위:

```text
1. Memory
2. Scheduler
3. Invest
4. Japanese Shorts
5. Music YouTube
6. Default Brain
```

`jarvis/agents` 폴더에는 전문 업무를 맡는 Agent가 있습니다.

- `invest.py`: 주식/투자 관련 명령 담당
- `japanese_shorts.py`: 일본어/쇼츠 관련 명령 담당
- `music_youtube.py`: 음악/유튜브 관련 명령 담당
- `memory.py`: 메모 저장, 조회, 검색, 삭제 담당
- `scheduler.py`: 일정/예약 기능을 위한 Stub

`jarvis/memory/store.py`는 Memory Agent가 사용하는 로컬 저장 기능을 담당합니다.

메모는 `data/memory.txt`에 저장됩니다. 이 파일은 개인 데이터이므로 Git에는 올리지 않습니다.

## 실행 방법

VS Code 터미널에서 실행합니다.

```powershell
cd C:\Projects\Jarvis
python main.py
```

실행하면 아래처럼 명령을 입력할 수 있습니다.

```text
================================
Jarvis v0.3.0-beta.7
================================
Jarvis >
```

## 현재 가능한 명령어 예시

Brain 라우팅 확인:

```text
주식 분석
SCHD 배당
일본어 쇼츠
일본어 번역
음악 유튜브
노래 만들어줘
일정 예약
```

Memory Agent:

```text
기억해 내 이름은 Chris
기억해 VOO 매일 1달러 매수
메모 보여줘
메모 검색 Chris
최근 메모
메모 개수
메모 삭제 2
3번 삭제
메모 전체 삭제
```

종료:

```text
exit
```

Command System:

```text
내 이름은 Chris야.
내 이름이 뭐였지?
안녕
오늘 뭐해?
chat 안녕
help
status
version
exit
```

## 테스트 방법

Python 문법 검사:

```powershell
python -m py_compile main.py
```

프로젝트 컴파일 확인:

```powershell
python -m compileall main.py jarvis config tests
```

테스트 실행:

```powershell
python -m unittest discover tests
```

## GitHub Actions(CI)

GitHub Actions가 구축되어 있습니다.

`git push`를 하면 GitHub에서 자동으로 아래 작업을 실행합니다.

```text
1. Python 문법 검사
2. 프로젝트 컴파일 확인
3. 테스트 실행
```

CI 설정 파일:

```text
.github/workflows/ci.yml
```

## GitHub CLI 사용 방법

GitHub CLI 설치 확인:

```powershell
gh --version
```

GitHub 로그인 상태 확인:

```powershell
gh auth status
```

GitHub Actions 실행 목록 확인:

```powershell
gh run list
```

최신 실행 자세히 보기:

```powershell
gh run view
```

실패 로그 확인:

```powershell
gh run view --log
```

## 개발 흐름

Jarvis는 아래 흐름으로 개발합니다.

```text
1. 기능 목표 정하기
2. 변경 전 계획 확인하기
3. 코드 또는 문서 수정하기
4. 로컬 테스트 실행하기
5. git commit 만들기
6. git push 하기
7. GitHub Actions 성공 확인하기
```

자세한 개발 흐름은 `DEVELOPMENT_WORKFLOW.md`를 참고합니다.
