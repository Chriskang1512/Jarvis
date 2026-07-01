# Jarvis

Python 기반 개인 AI 비서 프로젝트입니다.

Jarvis는 사용자의 채팅 명령을 받아 분석하고, 작업 성격에 맞는 하위 Agent에게 일을 배정하는 구조로 개발합니다.

## 목표

1. 사용자가 채팅으로 Jarvis에게 명령합니다.
2. Jarvis의 Brain이 명령을 분석합니다.
3. Brain은 하위 Agent에게 작업을 배정합니다.
4. 하위 Agent는 각각 전문 업무를 처리합니다.
5. 처음에는 로컬 CLI 채팅 버전으로 시작합니다.
6. 이후 음성인식, YouTube 업로드, 투자 분석, 일본어 쇼츠 제작, 음악 채널 자동화로 확장합니다.

## 현재 프로젝트 구조

```text
.
|-- main.py
|-- README.md
|-- .gitignore
|-- requirements.txt
|-- config
|   `-- settings.py
|-- docs
|   `-- overview.md
|-- jarvis
|   |-- __init__.py
|   |-- assistant.py
|   |-- agents
|   |   |-- __init__.py
|   |   |-- invest.py
|   |   |-- japanese_shorts.py
|   |   `-- music_youtube.py
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
|-- tests
|   `-- .gitkeep
`-- logs
    `-- .gitkeep
```

## 폴더 역할

- `main.py`: Jarvis CLI 프로그램의 시작 파일입니다.
- `jarvis/brain`: 사용자의 명령을 분석하고 어떤 Agent가 처리할지 결정합니다.
- `jarvis/agents`: 전문 작업을 담당하는 하위 Agent 모음입니다.
- `jarvis/memory`: 대화와 작업 기록을 저장합니다.
- `jarvis/utils`: 여러 곳에서 함께 사용할 작은 도구 함수를 저장합니다.
- `jarvis/models`: 나중에 데이터 구조나 모델 클래스를 저장합니다.
- `config`: 프로젝트 설정을 저장합니다.
- `logs`: 나중에 실행 로그를 저장할 폴더입니다.
- `docs`: 프로젝트 설명 문서를 저장합니다.
- `tests`: 기능이 늘어났을 때 테스트 코드를 저장합니다.
- `requirements.txt`: 프로젝트에 필요한 Python 패키지를 기록합니다.

## 초기 Agent

- `Brain`: Jarvis 메인 컨트롤러
- `Invest Agent`: 투자 분석 담당
- `JapaneseShorts Agent`: 일본어 쇼츠 제작 담당
- `MusicYoutube Agent`: 음악 유튜브 업로드 자동화 담당
- `Memory`: 대화와 작업 기록 저장

## 실행 방법

프로젝트 루트에서 실행합니다.

```bash
python main.py
```

실행하면 아래처럼 명령을 입력할 수 있습니다.

```text
Hello, Jarvis
Type a command, or type 'exit' to quit.
You >
```

## 테스트해볼 명령

```text
help
invest report
japanese shorts idea
music youtube upload
exit
```

## 개발 단계

1. CLI 채팅 입력 구조 만들기
2. Brain에서 명령 분석하기
3. Agent별 기본 응답 만들기
4. Memory에 대화 기록 저장하기
5. Agent 기능을 하나씩 실제 기능으로 확장하기
6. 설정 파일과 로그 기능 강화하기
7. AI API 연결하기
8. 음성인식, YouTube 자동화, 투자 분석, 일본어 쇼츠 제작 기능 추가하기

## 현재 상태

현재 버전은 초보자가 이해하기 쉬운 기본 구조입니다. 실제 AI 기능은 아직 연결하지 않았고, Agent별 기본 응답과 CLI 입력 흐름만 준비되어 있습니다.
