# Jarvis Development Workflow

Jarvis 프로젝트를 개발할 때 사용하는 기본 작업 흐름입니다.

이 문서는 초보자도 같은 순서로 따라 할 수 있도록 작성했습니다.

## 1. Jarvis 개발 기본 흐름

Jarvis는 작은 기능을 하나씩 추가하면서 안전하게 키웁니다.

기본 흐름은 아래와 같습니다.

```text
1. 만들 기능 정하기
2. Codex에게 작업 요청하기
3. 변경 전 계획 확인하기
4. 파일 수정하기
5. 로컬 테스트 실행하기
6. Git commit 만들기
7. GitHub로 push 하기
8. GitHub Actions 결과 확인하기
```

## 2. Codex에게 작업을 요청하는 방법

Codex에게 요청할 때는 아래 내용을 같이 적으면 좋습니다.

```text
목표:
무엇을 만들고 싶은지 설명합니다.

요구사항:
꼭 지켜야 할 조건을 적습니다.

예시:
사용자가 어떤 명령을 입력하고, 어떤 결과가 나와야 하는지 적습니다.

주의사항:
수정하면 안 되는 파일이나 지켜야 할 규칙을 적습니다.
```

예시:

```text
Memory Agent에 메모 검색 기능을 추가해주세요.

요구사항:
- 변경 전 계획을 먼저 보여주세요.
- 새 파일은 만들지 마세요.
- 함수마다 주석을 작성해주세요.

예시:
메모 검색 Chris
-> Chris가 포함된 메모만 출력
```

## 3. 변경 전 계획 검토 규칙

Jarvis 프로젝트에서는 파일을 수정하기 전에 먼저 계획을 확인합니다.

계획에는 아래 내용이 있어야 합니다.

```text
1. 어떤 파일을 만들거나 수정할지
2. 왜 그 파일을 수정하는지
3. 새 파일을 몇 개 만드는지
4. 테스트는 어떻게 할지
```

중요한 규칙:

```text
- 내 승인 없이 파일을 5개 이상 만들지 않습니다.
- Python만 사용합니다.
- 초보자가 이해할 수 있게 작성합니다.
- 복잡한 디자인 패턴은 사용하지 않습니다.
```

## 4. 테스트 명령어

VS Code 터미널에서 프로젝트 폴더로 이동합니다.

```powershell
cd C:\Projects\Jarvis
```

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

Jarvis CLI 실행:

```powershell
python main.py
```

## 5. Git commit / push 방법

현재 변경 상태 확인:

```powershell
git status
```

변경 파일 스테이징:

```powershell
git add .
```

커밋 만들기:

```powershell
git commit -m "작업 내용 설명"
```

GitHub로 push:

```powershell
git push origin main
```

최근 커밋 확인:

```powershell
git log --oneline -3
```

## 6. GitHub Actions 확인 방법

GitHub Actions는 `git push` 후 자동으로 실행됩니다.

터미널에서 확인:

```powershell
gh run list
```

최신 실행 자세히 보기:

```powershell
gh run view
```

실패 로그 보기:

```powershell
gh run view --log
```

GitHub 웹사이트에서 확인:

```text
1. GitHub 저장소로 이동
2. Actions 탭 클릭
3. Jarvis CI 클릭
4. 최신 실행 결과가 초록 체크인지 확인
```

## 7. 자주 생기는 문제

### 새 프로그램 설치 후 VS Code 재시작 필요

GitHub CLI 같은 새 프로그램을 설치한 뒤에는 VS Code 터미널이 바로 인식하지 못할 수 있습니다.

해결 방법:

```text
1. VS Code를 완전히 종료합니다.
2. VS Code를 다시 엽니다.
3. 터미널을 새로 엽니다.
4. 명령어를 다시 실행합니다.
```

### PATH 반영 문제

프로그램을 설치했는데 명령어를 찾을 수 없다고 나오면 PATH가 아직 반영되지 않은 것입니다.

예시:

```text
gh : The term 'gh' is not recognized
```

해결 방법:

```text
1. VS Code를 재시작합니다.
2. 그래도 안 되면 컴퓨터를 재부팅합니다.
3. 다시 gh --version을 실행합니다.
```

확인 명령어:

```powershell
gh --version
```

### GitHub CLI 로그인 확인

GitHub CLI가 설치되어 있어도 로그인이 안 되어 있으면 Actions 조회가 안 될 수 있습니다.

로그인 상태 확인:

```powershell
gh auth status
```

로그인이 안 되어 있으면:

```powershell
gh auth login
```

로그인 후 다시 확인:

```powershell
gh run list
```

## 8. 추천 개발 습관

기능을 크게 만들기보다 작게 나눠서 개발합니다.

추천 흐름:

```text
1. 작은 기능 하나 만들기
2. 로컬 테스트하기
3. 커밋하기
4. push 하기
5. GitHub Actions 확인하기
6. 다음 기능으로 넘어가기
```

이 흐름을 지키면 Jarvis를 안정적으로 키울 수 있습니다.
