# Jarvis Roadmap

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
- [ ] Plugin System
- [ ] LLM Abstraction
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
