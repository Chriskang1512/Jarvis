# Jarvis Roadmap

## Internal Milestone - Jarvis Core v1 Complete

Status: Complete after v0.5.0 Beta.5.3 Follow-up Conversation Mode.

External versioning can continue through v0.5.0, but the internal architecture
baseline is now:

```text
Jarvis Core
  |
  v
Runtime -> Planner -> Execution -> Router -> Dispatcher -> Diagnostics
  |
  v
Provider -> VoiceProfile -> Conversation Lifecycle
```

Core is now considered stable enough that future work should primarily grow
Jarvis through abilities rather than by adding more core scaffolding.

Guiding rule:

```text
Core is the brain.
Abilities are the fingers.
n8n is the external hand for integrations.
```

## Ability Era

Future development moves from `Core` to `Ability`.

```text
          Jarvis Core
               |
    +----------+----------+
    |                     |
    v                     v
 Native Ability     Integration Ability
    |                     |
    v                     v
 Memory             Gmail
 Japanese           Calendar
 Finance            Discord
 Hotel              Notion
 Creator            Slack
 Vision             Home Assistant
                          |
                          v
                     n8n Bridge
```

Native Abilities live inside Jarvis and can own local logic, models, prompts,
domain rules, and first-party tools.

Examples:

- Memory
- Japanese
- Finance
- Hotel
- Vision
- Creator Logic

Integration Abilities connect Jarvis to external services. These should prefer
the automation-provider path and execute through the `n8n Bridge` unless there
is a clear product reason to build a direct native integration.

Examples:

- Gmail
- Google Calendar
- Discord
- Notion
- Slack
- Home Assistant

This keeps Jarvis Core clean: Core decides, plans, routes, and speaks; Native
Abilities provide internal capabilities; Integration Abilities delegate external
work through automation infrastructure.

## v0.6.0 - Ability Expansion

Status: In progress.

Completed Sprint milestones:

- [x] Sprint 1 - Weather Ability foundation
- [x] Sprint 2 - Memory Ability foundation
- [x] Sprint 3 - Calendar Ability foundation
- [x] Sprint 4 - Native Reminder / Scheduler
- [x] Sprint 5 - Runtime Tool Dispatcher
- [x] Sprint 6 - Runtime Planner / Multi-Tool Planning
- [x] Sprint 7 - n8n Integration Bridge Foundation
- [x] Sprint 8 - AI Intent Parser / NLU Foundation
- [x] Sprint 9 - Agent Runtime Task Engine
- [x] Sprint 10 - Calendar Conversation Task Engine
- [x] Sprint 11 - Conversation Update Engine
- [x] Sprint 12 - STT v2 / Replay / Metrics
- [x] Sprint 13 - Semantic Transcript Layer
- [x] Sprint 14 - Contact Memory Foundation
- [x] Sprint 15 - Core Event Bus Foundation
- [x] Sprint 16 - Todo Ability Vertical Slice
- [x] Sprint 17.0 - Google OAuth + Google Calendar Read Vertical Slice

Sprint 17.0 closure:

```text
Voice
  |
STT
  |
Semantic
  |
Intent / Planner
  |
Dispatcher
  |
Calendar Ability
  |
CalendarProvider
  |
GoogleCalendarProvider
  |
Structured Result
  |
TTS
```

Verified:

- Google OAuth completes against a real user account.
- Google Calendar read-only provider returns internal Calendar models.
- Today, next week, and next-event queries work through the Jarvis runtime.
- Mock Calendar remains the default provider and regression path.
- Sensitive client secrets and tokens are ignored by git.
- Full regression suite passes.

Sprint 7 closure:

```text
STT
  |
User Vocabulary Correction
  |
Rule Parser / Planner
  |
Dispatcher
  |
Integration Ability
  |
n8n Bridge Provider
```

Verified:

- Integration Bridge contract is stable.
- Mock Provider is stable for offline tests.
- `system.health` and `system.echo` run through the Integration Ability.
- Permission, validation, provider capability, retry contract, correlation IDs,
  and metrics paths are covered.
- Planner -> Dispatcher -> Integration Ability flow is functional.

Sprint 7 known boundary:

```text
Ambiguous spoken phrases are no longer a Bridge bug.
They are an NLU problem.
```

Continuing to add regex aliases for every phrase such as `n8n`,
`system echo`, `external automation`, or misheard Korean variants has
diminishing returns. The next step should be a natural-language intent layer.

Sprint 8 foundation:

```text
STT
  |
User Vocabulary Correction
  |
AI Intent Parser
  |
Structured Intent
  |
Planner
  |
Dispatcher
  |
Ability
```

AI Intent Parser rule:

```text
AI structures intent.
Core validates and executes.
```

The AI parser may convert a phrase such as:

```text
외부 자동으로 테스트 메시지 보내줘
```

into:

```json
{
  "intent": "integration.execute",
  "workflow_key": "notification.test",
  "payload": {
    "message": "테스트 메시지"
  }
}
```

But execution must still go through Registry validation, Permission Layer,
confirmation rules, Dispatcher, Provider, and result validation.

Implemented Sprint 8 baseline:

- `jarvis.runtime.intent` parser package.
- Structured Intent models.
- Intent Registry.
- Rule / AI / Hybrid parser split.
- AI JSON output parsing through the LLM provider abstraction.
- Validation layer for registry, required parameters, date/time, forbidden URLs,
  unsupported conditionals, and invalid action combinations.
- Confidence policy and clarification handling.
- Planner conversion from Structured Intent to ExecutionPlan.
- Debug traces for `[Intent]`.

Remaining future work:

- Add true provider-level Structured Outputs / Function Calling support where the
  selected LLM provider exposes it.
- Wire AI Intent Parser into the default voice bootstrap behind
  `JARVIS_AI_INTENT_ENABLED`.
- Expand conversation follow-up merging for clarification answers.
- Keep Rule Parser for fast, deterministic high-confidence commands.

## v0.5.0 - Local Assistant Runtime

Jarvis v0.5.0 connects the usable assistant pipeline:

```text
Voice/Text/CLI/API -> Intent -> Planner -> Plan -> Permission -> Router -> Dispatcher -> Execution Metrics -> Response -> Diagnostics
```

Beta plan:

- [x] Beta.1 Intent Runtime Foundation
- [x] Beta.2 Tool Router Integration
- [x] Beta.2.5 Runtime Visibility / Dev Console
- [x] Beta.3 Planner Foundation
- [x] Beta.4 Execution Engine Enhancement
- [x] Beta.5 OpenAI Runtime Provider
- [ ] Beta.6 Diagnostics Console v2
- [ ] Beta.7 Real Scenario Test Pack
- [ ] v0.5.0 Release

Completion target:

- [x] Wake-word time requests route to `time.lookup`
- [x] safe tool execution can produce a spoken response
- [x] confirm-required tools stop before execution
- [x] diagnostics records the end-to-end trace
- [x] Intent object standardized for future keyword/rule/OpenAI/local LLM parsers
- [x] RuntimeContext added for source/session/user/conversation metadata
- [x] Intent parameters are immutable for diagnostics and replay safety
- [x] RuntimeResult object carries intent, permission, tool, response, diagnostics, and elapsed time
- [x] permission is evaluated before tool routing
- [x] Collector publishes `runtime.completed`
- [x] Collector publishes runtime stage events
- [x] Runtime is shared by voice, text, CLI, and API callers
- [x] Runtime Dev Console renders input, intent, permission, tool, fallback, response, elapsed time, runtime ID, and session ID
- [x] Runtime Dev Console shows `Jarvis Runtime` and current runtime version in the header
- [x] Runtime Dev Console supports `theme="simple"` as the first renderer theme
- [x] Planner creates a single-step Plan from one Intent
- [x] Plan includes a short ID for diagnostics and replay
- [x] PlanStep includes execution status
- [x] Runtime executes through Planner before ToolRouter
- [x] Runtime publishes plan.created, plan.started, and plan.completed
- [x] Runtime Dev Console renders Plan ID, goal, steps, and step status
- [x] RetryPolicy contract exists with default retry count of zero
- [x] ExecutionContext separates plan execution metadata from RuntimeContext
- [x] RuntimeResult carries execution metrics for execution, router, dispatcher, retry, and fallback
- [x] PlanStep includes timeout_ms for future timeout handling
- [x] Runtime reserves CANCELLED execution status
- [x] Runtime exposes execute_parallel(plan) as a future interface placeholder
- [x] Runtime Dev Console renders execution metrics, retry, timeout, elapsed, and fallback state
- [x] OpenAIChatProvider implements the existing chat provider contract
- [x] `chat_provider` config can select Mock or OpenAI without changing Runtime
- [x] Runtime Dev Console renders active chat provider
- [x] General conversation can use OpenAI while tool requests still use Runtime -> ToolRouter
- [x] TTS debug output shows full response text, exact TTS input, and character length
- [x] TTS receives normalized plain text instead of raw Markdown
- [x] VoiceProfile separates Jarvis voice identity from TTS provider implementation
- [x] VoiceRegistry can resolve built-in profiles such as Jarvis and Friday
- [x] OpenAI TTS provider can generate audio through the shared TTS provider contract
- [x] Follow-up Conversation Mode keeps Jarvis awake after speaking
- [x] ConversationSession tracks IDLE, LISTENING, THINKING, SPEAKING, FOLLOW_UP, and CLOSED
- [x] Runtime Dev Console renders conversation session, state, and remaining follow-up time
- [ ] interactive user confirmation prompt

Beta.2 focus:

- [x] remove Brain router dependency from IntentRuntime
- [x] formalize `ToolRouter.resolve(intent)`
- [x] add `ToolRoute` as the common route contract
- [ ] standardize PermissionLayer check around tool and intent
- [ ] keep Runtime as flow manager, Router as tool selector, Dispatcher as executor

Beta.3 reserved direction:

```text
User -> Runtime -> Planner -> Plan -> ToolRouter -> Executor
```

Goal-based multi-step execution should let Jarvis split one request into
ordered tool steps, such as Weather -> Condition -> Calendar.

Beta.3 completed foundation:

```text
User -> Runtime -> Planner -> Plan -> ToolRouter -> Dispatcher -> RuntimeResult
```

The planner is intentionally rule-based and single-step in Beta.3.

Beta.4 completed foundation:

```text
Runtime -> Planner -> Plan -> ExecutionContext -> ToolRouter -> Dispatcher -> RuntimeResult
```

Execution remains single-step and sequential, but now has contracts for retry
policy, step timeout, cancellation status, metrics, and future parallel
execution.

Beta.5 completed foundation:

```text
General Chat -> ChatProvider(OpenAI)
Tool Intent  -> Runtime -> Planner -> ToolRouter -> Dispatcher
```

Beta.5 intentionally excludes streaming, function calling, tool calling through
OpenAI, memory, weather APIs, and fallback provider switching.

Beta.5.1 TTS Debug:

```text
LLM Response -> TTS Input -> TTS playback -> len(tts_text)
```

This makes the first demo easier to diagnose when text reaches GPT correctly
but TTS output is unclear or truncated.

TTS Markdown normalization now happens only at the TTS boundary. Runtime
responses and console diagnostics keep the original model response available.

Pyttsx3 playback queues all normalized speech chunks before a single playback
run so multi-line responses do not stop after the first line on Windows SAPI.

Beta.5.2 Voice Identity Foundation:

```text
VoicePipeline -> TTSProvider -> VoiceProfile -> Playback
```

Jarvis can now switch voice identity by profile while keeping the same
VoicePipeline contract. OpenAI TTS is the first real provider behind this
abstraction; Edge TTS remains a future candidate.

`jarvis_default` is defined as a JARVIS-inspired original voice identity:
British-inspired, calm, composed, witty, and styled as a private butler / hotel
concierge.

Beta.5.3 Follow-up Conversation Mode:

```text
Wake -> Listening -> Thinking -> Speaking -> Follow-up -> Closed -> Idle
```

Jarvis can now accept additional voice turns during a configurable follow-up
window without requiring the wake word again. Runtime remains session-agnostic;
the conversation lifecycle lives in the Voice layer.

---

Jarvis 프로젝트는 날짜가 아니라 마일스톤 기준으로 버전을 관리합니다.

## Sprint Codenames

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

## Version Roadmap

## v0.4.0 Stable Release

v0.4.0 is released as the stable architecture baseline for Jarvis Framework.

- [x] Release Candidate promoted to stable
- [x] Full test suite passing
- [x] Public API list documented
- [x] v0.5 candidates separated into Next / Future

Stable release status: v0.4.0.

---

## v0.4.0 Release Candidate

v0.4.0 RC does not add new features. It freezes the Beta.1-Beta.7 architecture
for stable release.

- [x] Planner reviewed
- [x] Execution Graph reviewed
- [x] Execution Kernel official terminology documented
- [x] Result Merge reviewed
- [x] Voice Integration reviewed
- [x] Scheduler Foundation reviewed
- [x] Agent Runtime reviewed
- [x] Public API list documented
- [x] Import boundaries verified by tests
- [x] v0.4.0 Release Note draft added
- [x] ADR 0018-0021 reviewed
- [x] Full test suite passing

Release Candidate status: promoted to v0.4.0 stable.

---

## Next / Future: v0.5 Candidates

v0.5 candidates are intentionally outside the v0.4.0 RC scope.

- [ ] Permission Layer
- [ ] Memory Foundation
- [ ] Tool Router
- [ ] Plugin System
- [ ] First real tool calling
- [ ] OpenAI Voice Provider actual implementation
- [ ] Real audio playback
- [ ] Persistence layer
- [ ] EventBus async fan-out

---

## Future: v0.5 - Capability Collaboration

Jarvis moves from adding independent capabilities to making capabilities
collaborate.

The goal changes from:

```text
Add Capability
```

to:

```text
Plan Task
  |
Select Capabilities
  |
Run Multiple Tools
  |
Merge Outputs
  |
Complete Work
```

This is where Jarvis starts becoming an agent that can combine Japanese,
Finance, Creator, Hotel, and future capabilities into one completed workflow.

- [ ] Multi-Tool Planner
- [ ] Cross-capability task planning
- [ ] Tool result chaining
- [ ] Shared execution context
- [ ] Planner diagnostics

---

## v0.4 Beta - Capability Orchestration

Jarvis starts living at home: capabilities collaborate instead of only answering
one tool at a time.

- [x] v0.4-beta.1 Intent Planner
- [x] v0.4-beta.2 Execution Graph
- [x] v0.4-beta.3 Capability Context
- [x] v0.4-beta.4 Result Merge
- [x] v0.4-beta.5 Voice Integration
- [x] v0.4-beta.6 Scheduler Foundation
- [x] v0.4-beta.7 Agent Runtime

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

Beta.5 Voice Integration entry conditions:

- [x] `UnifiedResult.summary` is stable for Voice output
- [x] UI can render `results`, `warnings`, `errors`, and `metadata`
- [x] Result order follows plan execution order
- [x] Partial results are preserved when one node fails
- [x] Summary keeps warning/error detail out of voice text
- [x] Diagnostics-ready metadata includes execution, plan, node, status, timing, and counts

Voice Integration note:

- [x] Voice pipeline mock STT smoke verified
- [x] Config contract prepared for `stt.provider`
- [x] `UnifiedResult.summary` to `VoiceResult` service contract
- [x] `VoiceProvider` interface
- [x] `MockVoiceProvider`
- [x] Provider DI test coverage
- [x] Voice boundary tests proving Planner, Execution, and Capability are not imported
- [x] OpenAI voice provider placeholder
- [x] Audio playback deferred beyond Beta.5
- [ ] Harden microphone input provider
- [ ] Add OpenAI STT provider implementation
- [ ] Add device selection and microphone diagnostics

---

## v0.4.0-beta.5 - Voice Integration

Jarvis prepares to speak by converting unified responses into voice results.
Beta.5 does not play audio through speakers.

```text
UnifiedResult
  |
VoiceService
  |
VoiceProvider
  |
VoiceResult
```

- [x] `voice/` service contract
- [x] `VoiceService`
- [x] `VoiceProvider` protocol
- [x] `VoiceResult`
- [x] `MockVoiceProvider`
- [x] OpenAI voice provider placeholder
- [x] `UnifiedResult.summary` only is sent to VoiceProvider
- [x] Provider dependency injection
- [x] Voice boundary tests
- [x] README update
- [x] ADR 0019 Voice Integration Architecture

Beta.5 close status: implemented.

Beta.6 entry: Scheduler can depend on `UnifiedResult` / `VoiceResult` contracts
without taking a dependency on Planner, Execution Graph, or Capabilities.

---

## v0.4.0-beta.7 - Agent Runtime

AgentRuntime is not the executor. It is the Runtime Layer that manages the
lifecycle between Scheduler and the Execution Kernel.

Jarvis adds a minimal runtime layer that coordinates Scheduler and Execution
Kernel through manual ticks.

```text
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

- [x] `jarvis.agent_runtime` module
- [x] `AgentRuntime`
- [x] `AgentRuntimeState`
- [x] `AgentTickResult`
- [x] `ExecutionKernel` protocol
- [x] explicit `start()` / `stop()` lifecycle
- [x] manual `tick(now)` only
- [x] Scheduler due check coordination
- [x] Scheduler trigger coordination
- [x] task-level failure remains isolated by Scheduler
- [x] runtime-level failure state when Scheduler itself fails
- [x] boundary tests proving Runtime does not import Planner, Voice, or Capabilities
- [x] ADR 0021 Agent Runtime Architecture

Explicitly out of scope:

- [ ] background thread
- [ ] asyncio loop
- [ ] daemon
- [ ] autonomous planning loop
- [ ] direct Planner calls
- [ ] direct Voice calls
- [ ] direct Capability calls
- [ ] Memory write loop
- [ ] automatic voice playback

Beta.7 close status: implemented.

---

## v0.4.0-beta.6 - Scheduler Foundation

Beta.6의 목표는 시간을 흐르게 만드는 것이 아니라, 예약 Task의 Lifecycle을
모델링하는 것이다.

Jarvis models scheduled task lifecycle without background execution.

```text
ScheduleRequest
  |
Schedule
  |
ScheduledTask
  |
TaskState
  |
Scheduler
  |
due_tasks(now)
  |
ExecutionRunner.run_unified()
  |
UnifiedResult
```

- [x] `jarvis.scheduler` module
- [x] `ScheduleRequest`
- [x] `Schedule`
- [x] `ScheduledTask`
- [x] `TaskState` enum
- [x] `Scheduler` protocol
- [x] `InMemoryScheduler`
- [x] `InMemoryTaskStore`
- [x] `SystemClock`
- [x] `FixedClock`
- [x] one-shot `run_at` schedule support
- [x] `ScheduledTask.is_due(now)`
- [x] `Scheduler.get()`
- [x] `Scheduler.cancel()`
- [x] `due_tasks(now)`
- [x] manual `trigger_due(now)`
- [x] `ExecutionRunner.run_unified()` integration by dependency injection
- [x] tests for lifecycle, due filtering, cancellation, trigger success, trigger failure, store isolation, and deterministic clock
- [x] ADR 0020 Scheduler Foundation Architecture

Explicitly out of scope:

- [ ] background thread
- [ ] asyncio loop
- [ ] cron parser
- [ ] recurring schedule
- [ ] interval schedule
- [ ] conditional schedule
- [ ] OS scheduler
- [ ] Windows Scheduler
- [ ] background daemon
- [ ] real notification delivery
- [ ] automatic voice playback

Beta.6 close status: implemented.

Beta.7 entry: Agent Runtime can ask Scheduler for due tasks and execute them
without owning scheduling lifecycle rules.

---

## v0.4.0-beta.1 - Intent Planner Contract

Jarvis defines the first Capability Orchestration contract.

- [x] Intent Planner package
- [x] Stable planning contract with `plan_id` and `planner_version`
- [x] Graph-shaped output with nodes and edges
- [x] Sequential execution mode only
- [x] Capability-level planning only
- [x] Permission mode marking
- [x] Planner design rules documented
- [x] Existing Alpha capability regressions

---

## v0.4.0-beta.2 - Execution Graph Runtime

Jarvis executes validated capability plans sequentially for the first time.

- [x] Execution package
- [x] Execution Graph Runner
- [x] Metadata Capability Router
- [x] Node lifecycle states
- [x] Ordered node result list
- [x] Runner diagnostics trace
- [x] No merge
- [x] Runner architecture boundary tests

---

## v0.4.0-beta.3 - Capability Context

Jarvis passes previous node results through temporary execution context.

- [x] ExecutionContext contract
- [x] Runner-owned context lifecycle
- [x] Previous node result handoff
- [x] Context destroyed after execution
- [x] Capability boundary tests
- [x] Memory remains separate

---

## v0.4.0-beta.4 - Result Merge

Jarvis assembles multiple capability results into one user-facing response.

```text
Finance Result
  |
Japanese Result
  |
Creator Result
  |
Merged Response
```

- [x] `ResultMerger` interface
- [x] `DefaultResultMerger` implementation
- [x] Immutable `UnifiedResult`
- [x] Success, warning, and error merge rules
- [x] Ordered result collection preserving plan execution order
- [x] Partial result preservation on node failure
- [x] Voice-friendly summary without detailed warning/error text
- [x] Diagnostics-ready metadata
- [x] ExecutionGraph `run_unified()` integration
- [x] ADR 0018 Result Merge Architecture
- [x] Regression tests for Voice/UI readiness, ordering, partial failure, summary, and metadata

Beta.4 close status: approved.

Beta.5 entry: Voice can consume `UnifiedResult.summary` without knowing planner,
execution, capability, warning, error, or metadata internals.

---

## v0.4.0-alpha.7 - Life Capability Alpha

Jarvis gets its final v0.4 alpha capability: a memory-adjacent life assistant.

- [x] Life capability owns tools
- [x] `life_todo`
- [x] `life_reminder`
- [x] `life_routine`
- [x] `life_habit`
- [x] `life_reflection`
- [x] Reminder output is ready for future Scheduler handoff
- [x] Reflection can read Memory without owning Memory
- [x] Existing Japanese / Finance / Creator / Hotel / Core route regressions
- [ ] Multi-Tool Planning

---

## v0.4.0-alpha.6 - Hotel Capability Alpha

Jarvis gets its hospitality operations assistant capability.

- [x] Hotel capability owns tools
- [x] `hotel_schedule_planner`
- [x] `hotel_complaint_report`
- [x] `hotel_complaint_manual`
- [x] Korean natural language routing
- [x] Existing Japanese / Finance / Creator / Core route regressions
- [x] Life Capability Alpha
- [ ] Multi-Tool Planning

---

## v0.4.0-alpha.5 - Creator Capability Alpha

Jarvis gets its first creative engine capability.

- [x] Creator capability owns tools
- [x] `creator_lyrics`
- [x] `creator_music_prompt`
- [x] `creator_title`
- [x] `creator_description`
- [x] `creator_song_package`
- [x] Prompt assets as first-class capability resources
- [x] Local Creator-only song package orchestration
- [x] Hotel Capability Alpha
- [ ] Life Capability Alpha
- [ ] Multi-Tool Planning

---

## v0.4.0-alpha.4 - Finance Capability Alpha

Jarvis gets its second real capability.

- [x] Finance capability owns tools
- [x] `finance_compound`
- [x] `finance_average_price`
- [x] `finance_profit`
- [x] `finance_portfolio`
- [x] `finance_exchange`
- [x] Registry-driven Brain routing
- [x] Japanese routing regression
- [x] Alpha Architecture Review
- [ ] Hotel Capability Alpha
- [x] Creator Capability Alpha
- [ ] Life Capability Alpha
- [ ] Multi-Tool Planning

---

## v0.4.0-alpha.3 - Japanese Capability Alpha

Jarvis gets its first real capability.

- [x] Japanese capability owns tools
- [x] `japanese_translate`
- [x] `japanese_grammar`
- [x] `japanese_reply`
- [x] `japanese_review`
- [x] Registry-driven Brain routing
- [x] Memory-backed review fallback path
- [ ] Speech / shadowing
- [ ] Spaced repetition engine
- [ ] Full JLPT curriculum

---

## v0.4.0-alpha.2 - Capability Plugin Framework

Jarvis organizes future powers as independent capabilities.

- [x] CapabilityMetadata
- [x] CapabilityRegistry
- [x] CapabilityLoader
- [x] Automatic capability discovery
- [x] Creator capability skeleton
- [x] Finance capability skeleton
- [x] Hotel capability skeleton
- [x] Japanese capability skeleton
- [x] Life capability skeleton
- [x] Capability tool registration into ToolRegistry
- [x] Finance Capability Alpha
- [x] Japanese Capability Alpha
- [ ] Hotel Capability Alpha
- [ ] Creator Capability Alpha
- [ ] Multi-Tool Planning

---

## v0.4.0-alpha.1 - Brain Tool Routing

Jarvis starts turning plain chat into safe actions.

- [x] BrainToolRouter
- [x] Natural-language calculator routing
- [x] Natural-language time routing
- [x] Natural-language diagnostics routing
- [x] Natural-language memory-read routing
- [x] Safe tool execution before LLM fallback
- [ ] Agent-specific real capabilities
- [ ] Confirmation flow for non-safe actions

---

## v0.2.0-alpha.8 - Sprint 8 Wrap-up

Provider-agnostic architecture를 검증하고 beta 진입 전 기록을 정리하는 단계입니다.

- [x] ClaudeProvider
- [x] Provider Contract Test
- [x] ADR-0001 Core Never Knows Vendors
- [x] README 업데이트
- [x] ROADMAP 업데이트
- [x] CHANGELOG 업데이트
- [ ] Git Tag

---

## v0.2.0-beta.1 - Voice Pipeline Foundation

음성 파이프라인의 최소 기반을 만드는 단계입니다.

- [x] `voice_main.py`
- [x] `jarvis/voice` module
- [x] Wake Word
- [x] Microphone Input
- [x] STT Interface
- [x] TTS Interface
- [x] VoicePipeline
- [x] Provider 연결
- [x] Stage logging

---

## v0.2.0-beta.2 - Metadata Console

Provider 응답 메타데이터를 확인할 수 있게 만드는 단계입니다.

- [x] `diagnostics_main.py`
- [x] `jarvis/diagnostics` module
- [x] DiagnosticsCollector
- [x] DiagnosticsConsole
- [x] Session metadata
- [x] Provider metadata
- [x] Performance metadata
- [x] Pipeline status
- [x] Health status
- [x] Event log
- [x] provider_name
- [x] model
- [x] usage
- [x] finish_reason
- [x] created_at

---

## v0.2.0-beta.3 - Tool Calling

Jarvis가 실제 작업을 실행할 수 있는 기반을 만드는 단계입니다.

- [ ] Tool Interface
- [ ] Tool Registry
- [ ] Tool Dispatcher
- [ ] Command execution foundation

---

## v0.1.0 - Project Bootstrap

개발 환경과 기본 구조를 준비하는 단계입니다.

- [x] 개발 환경 구축 완료
- [x] Git
- [x] GitHub
- [x] VS Code
- [x] Python
- [x] Brain
- [x] Agent
- [x] Memory
- [x] GitHub Actions
- [x] GitHub CLI

---

## v0.2.0 - First Functional AI

첫 번째 실제 기능형 AI Agent를 만드는 단계입니다.

- [x] Event-driven Core architecture
- [x] Generic EventBus
- [x] JarvisState model
- [x] Console Adapter heartbeat
- [x] Command Interface
- [x] Command Registry
- [x] Command Dispatcher
- [x] HelpCommand / StatusCommand / VersionCommand / ExitCommand
- [x] ChatCommand
- [x] ChatService
- [x] MockChatProvider
- [x] Unknown input fallback to ChatCommand
- [x] PromptBuilder
- [x] Jarvis identity / personality / response style separation
- [x] Special modes
- [x] Provider-agnostic prompt generation
- [x] Configuration Layer
- [x] Provider / model / debug settings
- [x] JarvisConfig
- [x] ConfigurationLoader
- [x] ProviderFactory
- [x] OpenAIProvider
- [x] provider=openai support
- [x] OPENAI_API_KEY from .env
- [x] ClaudeProvider
- [x] provider=claude support
- [x] ANTHROPIC_API_KEY from .env
- [x] MemoryService
- [x] MockMemoryProvider
- [x] First memory conversation
- [ ] JSONMemoryProvider
- [ ] SQLiteMemoryProvider
- [ ] VectorMemoryProvider
- [ ] Rive-compatible visual layer planned
- [ ] Invest Agent 실제 기능
- [ ] Scheduler 실제 기능
- [ ] Memory 검색 개선
- [ ] 자연어 명령 분류 개선

---

## v0.3.0 - External Services

생각하고, 기억하고, 행동할 수 있는 AI로 발전하는 단계입니다.

## v0.3.0 Beta Blueprint

Goal:

Transform Jarvis from a conversational assistant into an extensible AI agent platform.

## v0.3.0-beta.1 - Voice Experience

사람처럼 대화하는 음성 경험의 기반을 만드는 단계입니다.

- [x] Voice Session 관리
- [x] Streaming-ready TTS 계약
- [x] Console TTS streaming chunks
- [x] Pyttsx3 TTS streaming chunks
- [x] Pyttsx3 default local voice provider
- [x] Piper local TTS provider candidate
- [x] Configurable TTS provider selection
- [x] TTS latency tracking
- [x] Interrupt-ready session flag
- [x] Voice diagnostics event publish
- [ ] OpenAI TTS Provider
- [ ] Real interrupt handling

Development Principles:

1. Architecture First
   - 기능보다 구조를 먼저 만듭니다.

2. Extensibility
   - 나중에 기능을 추가해도 기존 코드를 크게 수정하지 않습니다.

3. Safety by Design
   - 권한은 처음부터 아키텍처에 포함합니다.
   - Permission Layer는 나중에 덧붙이는 기능이 아니라 핵심 설계 요소입니다.

PM Task Order:

```text
3.1 Voice Experience
  |
3.2 Conversation Memory
  |
3.3 Tool Calling (Safe Only)
  |
3.4 Permission Layer
  |
3.5 Memory Store
  |
3.6 Plugin System
  |
3.7 LLM Abstraction
```

```text
Jarvis v0.3.0 Beta

|-- Beta 3.1 Voice Experience
|   `-- 실제 음성 입출력 완성
|
|-- Beta 3.2 Conversation Memory
|   `-- 현재 대화 기억
|
|-- Beta 3.3 Tool Calling
|   `-- AI가 기능을 호출하는 구조
|
|-- Beta 3.4 Permission Layer
|   `-- Tool 실행 권한 관리
|
|-- Beta 3.5 Memory Store
|   `-- 장기 기억 저장
|
|-- Beta 3.6 Plugin System
|   `-- 기능 확장 구조
|
`-- Beta 3.7 LLM Abstraction
    `-- OpenAI / Claude / Gemini / Local 교체 가능
```

의존 관계:

```text
Voice Experience
  |
Conversation Memory
  |
Tool Calling
  |
Permission Layer
  |
Memory Store
  |--------|
  |        |
Plugin   LLM Abstraction
System
```

v0.3.0의 목표:

- [ ] Voice Experience
- [x] Conversation Memory
- [x] Tool Calling
- [x] Permission Layer
- [x] Memory Store
- [x] Plugin System
- [x] LLM Abstraction
- [ ] Gmail
- [ ] Google Calendar
- [ ] Discord
- [ ] Telegram

---

## v0.5.0 - Automation

Jarvis가 사용자의 반복 작업을 자동으로 도와주는 단계입니다.

- [ ] 음성 명령
- [ ] 자동 실행
- [ ] 자동 투자 보조
- [ ] 자동 일정 관리

---

## v1.0.0 - Personal AI Assistant

실제 개인 AI 비서로 완성하는 단계입니다.

- [ ] 개인 비서 수준 완성
- [ ] 투자
- [ ] 일정
- [ ] 일본어
- [ ] 음악
- [ ] YouTube
- [ ] Memory
- [ ] 음성
