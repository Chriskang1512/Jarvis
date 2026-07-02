# Jarvis

Python 기반 개인 AI 비서 프로젝트입니다.

Jarvis는 사용자의 채팅 명령을 받아 Brain이 명령을 분석하고, 작업 성격에 맞는 Agent에게 일을 배정하는 구조로 개발합니다.

## Current Version

v0.1.0 - Project Bootstrap

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

아직 실제 AI API 연결은 하지 않았습니다.

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

## Core Design Principle

Jarvis는 event-driven architecture를 따릅니다.

Core는 누가 이벤트를 소비하는지 알지 않습니다.

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

- `help`
- `status`
- `version`
- `exit`

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
Jarvis v0.2.0-alpha.2
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
