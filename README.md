# SecurityLab AI v1

SecurityLab AI는 사용자가 소유한 로컬 합성 사이트에서 하나의 공개된 접근 통제 시나리오를 재현하고, 모델의 후보 판단과 증거 검증기의 확정 판정을 분리하는 독립 실험용 애플리케이션이다.

## 구현 범위

구현됨:

- 합성 계정 `user-a`, `user-b`, `admin`과 계정별 비공개 문서
- 동일 경로·동일 fixture를 사용하는 `vulnerable` / `fixed` target 모드
- 비밀번호 scrypt 해시, HttpOnly/SameSite 세션, target 전용 SQLite
- worker의 exact-origin/IP literal 정책, 불투명 세션 참조, 인증, redirect 차단, 응답/시간/누적 요청 한도, 취소
- mock provider 기반 실제 HTTP 검증 흐름과 별도 verifier
- 선택적 OpenAI Agents SDK provider. 모델 ID는 기본값을 만들지 않으며 키와 ID가 모두 필요
- controller FastAPI, local single-user 세션, CSRF/Origin 검사, SQLite WAL 이력, SSE, 취소, 재시작 시 `INTERRUPTED`
- React + TypeScript + Vite 대화·진행·결과·이력 UI와 same-origin 정적 배포
- worker Streamable HTTP MCP endpoint와 `MCPServerStreamableHttp` 기반 내부 client
- JSON/Markdown 보고서와 target-local 로그의 오프라인 상관 검증 CLI

구현하지 않음(2단계):

- Nmap inventory
- Playwright 공격 브라우저 및 UI 브라우저 E2E/스크린샷

이 둘은 stub tool로도 노출하지 않는다. `health`와 UI에는 `not_implemented`로만 표시된다.

## 신뢰 경계

```text
Windows browser
  -> controller /api (session + CSRF + Origin)
  -> SQLite (redacted conversation/run/evidence metadata)
  -> function worker API OR SDK-managed MCP
  -> worker policy + cumulative limits
  -> exact registered target origin
  -> synthetic target SQLite

target response text --X--> model / browser / public report
target-local DB/log   --X--> agent tools
```

controller는 계획·설명·보고서를 맡고 target HTTP는 worker만 수행한다. 모델과 브라우저는 URL, origin, 포트, 계정 credential, worker token, shell command, 정책을 변경할 수 없다. target의 본문은 비신뢰 데이터이며 worker가 합성 marker와 메타데이터만 추출한다.

## 로컬 설치

Python 3.12와 Node.js 22를 사용해 확인했다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-full.lock
cd frontend
npm ci
npm test
npm run build
cd ..
.\.venv\Scripts\python.exe -m pytest
```

Linux VM에서는 `.venv/bin/python`을 사용한다.

## 설정

`.env.example`을 참고하되 비밀값이 든 `.env`는 커밋하지 않는다. 최소한 controller와 worker에 같은 충분히 긴 `WORKER_TOKEN`을 넣고 controller에는 24자 이상의 `APP_SESSION_SECRET`을 넣는다. target과 worker에 동일한 `LAB_USER_A_PASSWORD`, `LAB_USER_B_PASSWORD`, `LAB_ADMIN_PASSWORD`를 설정한다. 이미 seed한 DB의 비밀번호를 바꿀 때는 target DB를 제거해 재-seed해야 하며 일반 reset은 문서 fixture를 보존한다.

기본 provider는 `mock`이다. live 실행은 다음 값이 모두 있어야 한다.

```dotenv
MODEL_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=계정에서 실제 사용 가능한 명시적 모델 ID
```

live provider의 키·모델 권한·API 호출이 실패하면 해당 run은 `FAILED`로 종료하며 mock으로 자동 전환하지 않는다.

OpenAI Agents SDK는 애플리케이션 안에서 실행되고 애플리케이션이 도구·상태·승인 경계를 소유하는 구조로 사용했다. 로컬 Streamable HTTP 연결은 Hosted MCP가 아니라 `MCPServerStreamableHttp`를 사용한다. 참고: [Agents SDK 개요](https://developers.openai.com/api/docs/guides/agents/sdk), [Agents SDK quickstart](https://developers.openai.com/api/docs/guides/agents/quickstart?lang=python), [MCP 안전 지침](https://developers.openai.com/api/docs/guides/tools-connectors-mcp).

## 실행

세 터미널 또는 세 VM에서 저장소 루트를 현재 디렉터리로 두고 실행한다.

```powershell
# target VM
$env:TARGET_MODE='vulnerable'
.\.venv\Scripts\python.exe -m uvicorn target.app:app --host 10.78.0.30 --port 8080

# worker VM
.\.venv\Scripts\python.exe -m uvicorn --factory worker.app:create_app_from_env --host 10.77.0.20 --port 9000

# controller VM (frontend/dist가 먼저 빌드되어 있어야 함)
.\.venv\Scripts\python.exe -m uvicorn --factory controller.api:create_app_from_env --host 192.168.56.10 --port 8000 --workers 1
```

`--workers 1`은 필수다. v1 작업 관리기는 프로세스 내부 단일 큐다. 브라우저에서 `http://192.168.56.10:8000`을 연다. worker와 target에는 UI용 Host-only NIC를 추가하지 않는다.

CLI:

```powershell
.\.venv\Scripts\python.exe -m controller.cli doctor
.\.venv\Scripts\python.exe -m controller.cli run --scenario access-control --target lab-web --provider mock --transport function
.\.venv\Scripts\python.exe -m controller.cli run --scenario access-control --target lab-web --provider mock --transport mcp
```

target의 모드는 target VM에서만 바꾸고 재시작한다. 세션과 관찰 로그 초기화도 target 로컬에서만 실행한다.

```powershell
.\.venv\Scripts\python.exe -m target.cli reset
```

## 판정

- `VULNERABLE`: user-b 본인 대조군이 성공하고, 인증된 user-a가 user-b의 정확한 합성 marker를 받았으며 target-local 기록이 연결됨
- `BLOCKED_BY_ACCESS_CONTROL`: user-b 대조군은 성공하지만 user-a의 같은 resource 요청은 403/404이고 marker가 없으며 target-local 기록이 연결됨
- `INCONCLUSIVE`: 로그인 실패, timeout, 500, 한도 초과, 대조군 실패, 전송 오류, 비결정적 응답

hash만으로 내용을 증명했다고 주장하지 않는다. 온라인 보고서가 `target_log_offline_pending`이면 최종 판정은 `INCONCLUSIVE`로 유지한다. target-local DB를 controller로 복사하지 말고 승인된 오프라인 평가 위치에서 다음 명령으로 상관 검증한다.

```powershell
.\.venv\Scripts\python.exe -m verifier.cli evaluate --run-dir reports/runs/<run_id> --local-evidence <target.sqlite3 경로>
```

## 데이터와 개인정보

모든 계정·문서·marker는 합성 fixture다. controller DB와 보고서에는 쿠키, Authorization, 비밀번호, API 키, worker token, 전체 HTML/본문을 저장하지 않는다. target DB는 controller DB와 공유하지 않는다. 보고서의 `evidence.json`도 정제 메타데이터만 포함한다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest
cd frontend
npm test
npm run build
```

테스트는 취약/수정/정상/없는 문서/로그인 오류, URL 정책, worker 인증, 누적 한도, DB 재시작·redaction·이벤트 순서, UI→작업→SSE→보고서, 실제 loopback MCP 연결·도구 목록·호출·인증/범위/취소/단절을 포함한다. VM 방화벽·NIC 격리와 실제 OpenAI 모델 품질은 이 로컬 테스트에 포함되지 않는다.

자세한 구조와 운영 절차는 `docs/`와 `reports/evidence_index.md`를 본다.
