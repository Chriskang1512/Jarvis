# Changelog

Jarvis 프로젝트의 변경 기록입니다.

이 문서는 Keep a Changelog 형식을 참고합니다.
Jarvis 버전은 날짜가 아니라 프로젝트 완성 단계, 즉 마일스톤 기준으로 증가합니다.

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
