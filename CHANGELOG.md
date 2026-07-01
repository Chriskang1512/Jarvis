# Changelog

Jarvis 프로젝트의 변경 기록입니다.

이 문서는 Keep a Changelog 형식을 참고합니다.
Jarvis 버전은 날짜가 아니라 프로젝트 완성 단계, 즉 마일스톤 기준으로 증가합니다.

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

### Changed

- Brain Routing 구조 개선
- Agent별 키워드 alias 구조 추가
- Memory 우선순위 개선
- Memory 저장 형식을 날짜/시간 포함 형식으로 개선
- Memory 조회 출력을 번호와 블록 형태로 개선
- 자연어 메모 삭제 명령 개선
- GitHub Actions로 자동 검사 흐름 추가
- 버전 관리를 날짜 기준이 아니라 마일스톤 기준으로 변경

### Fixed

- Memory Routing 버그 수정
- `기억해 VOO 투자`가 Invest가 아니라 Memory로 가도록 수정
- 없는 번호의 메모 삭제 시 예외 메시지 처리
- 자연어 삭제 명령 개선
