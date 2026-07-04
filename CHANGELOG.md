# Changelog

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
