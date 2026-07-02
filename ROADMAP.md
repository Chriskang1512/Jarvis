# Jarvis Roadmap

Jarvis 프로젝트는 날짜가 아니라 마일스톤 기준으로 버전을 관리합니다.

## Sprint Codenames

```text
Sprint 1  - The First Heartbeat
Sprint 2  - The First Command
Sprint 3  - The First Conversation
Sprint 4  - The First Personality
Sprint 5  - The First Configuration
Sprint 6  - The Second Brain
Sprint 7  - The First Memory
Sprint 8  - The First Tool
Sprint 9  - The First Voice
Sprint 10 - The First Face
```

## Version Roadmap

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
- [ ] Rive-compatible visual layer planned
- [ ] Invest Agent 실제 기능
- [ ] Scheduler 실제 기능
- [ ] Memory 검색 개선
- [ ] 자연어 명령 분류 개선

---

## v0.3.0 - External Services

외부 서비스와 연결하는 단계입니다.

- [ ] OpenAI API
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
