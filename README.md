# SecurityLab AI v1

SecurityLab AI는 사용자가 소유한 로컬 합성 사이트에서 등록된 접근 통제 시나리오를 재현하고, 모델의 후보 판단과 증거 검증기의 확정 판정을 분리하는 독립 실험용 애플리케이션이다. 현재 구조는 범용 모의해킹 에이전트가 아니라 **고정 시나리오 검증기 + 선택적 LLM 후보 생성기**다. 자유문은 URL·대상·도구·실행 순서를 바꾸지 않는다.

`access-control`은 기존 서버 로그 대조 경로이며 로그가 없으면 `INCONCLUSIVE`다. 새 `access-control-http`는 `lab-web`의 두 실습 계정과 명시적인 합성 private canary 구조를 사용하는 HTTP 전용 경로다. 독립 세션, 소유자 목록·상세, 교차 요청, 소유자/요청자 재조회를 검증하며 target DB·로그·모드나 모델 의견으로 판정하지 않는다. 보고서의 `verification_basis`로 두 경로를 구분한다. 일반 HTML 의미 비교나 임의 외부 사이트 테스트는 지원하지 않는다.

로컬 네 조합 자동 재현: `.\.venv\Scripts\python.exe scripts/run_http_verification.py`. 임시 loopback 서버와 DB를 사용하고 자신이 만든 서버만 종료한다. [HTTP 실행 가이드](docs/http_verification_runbook.md)와 [실제 실행 결과](reports/http_verification_results.md)를 참고한다.

실행 범위는 운영자 파일 `config/targets.json`의 schema 2.0 프로필로 관리한다. worker가 세션 생성 전과 HTTP 전송 직전에 계정·작업·경로·세션·실효 한도를 검사한다. 정책 변경은 worker 재시작 후 적용되며 `TARGET_BASE_URL`은 등록 origin과 일치해야 한다. 오프라인 검사: `.\.venv\Scripts\python.exe -m worker.cli check-policy`. [정책 형식·VM 갱신 절차](docs/scope_policy_runbook.md), [정책 검증 결과](reports/scope_policy_verification.md)를 참고한다. 과거 보고서의 정책 정보는 `legacy / 미기록`으로 유지한다.

## 구현 범위

구현됨:

- 합성 계정 `user-a`, `user-b`, `admin`과 계정별 비공개 문서
- 동일 경로·동일 fixture를 사용하는 `vulnerable` / `fixed` target 모드
- 비밀번호 scrypt 해시, HttpOnly/SameSite 세션, target 전용 SQLite
- worker의 exact-origin/IP literal 정책, 불투명 세션 참조, 인증, redirect 차단, 압축 전송/해제 후 스트리밍 응답 크기·시간·정확한 누적 요청 한도, 대기·진행 중 취소
- mock provider 기반 실제 HTTP 검증 흐름과 별도 verifier
- 선택적 OpenAI Agents SDK provider. 모델 ID는 기본값을 만들지 않으며 키와 ID가 모두 필요
- controller FastAPI, 초기 접근 토큰 인증, 무작위 만료 세션·SQLite 영속 logout 철회, CSRF/Origin/Host/client allowlist, SQLite WAL 이력, 전체 run timeout, SSE, 취소, 재시작 시 `INTERRUPTED`
- React + TypeScript + Vite provider 선택·대화/run 복원·비동기 대화/run identity guard·원자적 terminal snapshot·SSE 재연결/폴링 UI와 same-origin 정적 배포
- 등록 Host/Origin만 허용하는 worker Streamable HTTP MCP endpoint와 환경 프록시를 사용하지 않는 `MCPServerStreamableHttp` 내부 client
- run·request·method·path·account·marker·status를 다시 대조하는 오프라인 검증 CLI와 인증된 정제 결과 반영 API

구현하지 않음(2단계):

- Nmap inventory
- Playwright 공격 브라우저 및 UI 브라우저 E2E/스크린샷

이 둘은 stub tool로도 노출하지 않는다. `health`와 UI에는 `not_implemented`로만 표시된다.

## 신뢰 경계

```text
Windows browser
  -> controller /api (access token + expiring session + CSRF + Origin/Host/client allowlist)
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

검사 대상의 로그인·쿠키/Bearer 인증·목록·상세 응답 구조는 이제 운영자 API 어댑터로 선택한다. 기본 documents와 중첩 JSON records API를 같은 HTTP 검사 흐름으로 실행한다. [어댑터 설정 및 VM별 업데이트·실행 명령](docs/target_api_adapters.md), [로컬 8조합 및 거절 검증 결과](reports/api_adapter_verification.md)를 참고한다.

서비스별 `.env.controller.example`, `.env.worker.example`, `.env.target.example`을 각 VM의 해당 환경 파일로 복사하고 비밀값을 로컬에서 채운다. `python -m common.service_config check worker`는 네트워크 없이 검사하고, `serve worker`는 선택한 worker 파일만 전달하여 실행한다. controller/target도 같은 형식을 사용한다. [서비스별 API·인증 설정과 이전 절차](docs/service_configuration.md)를 참고한다. 기존 직접 Uvicorn/CLI 실행은 호환되지만 새 launcher의 파일 검사·환경 필터를 거치지 않는다.

`.env.example`을 참고하되 비밀값이 든 환경 파일은 커밋하지 않는다. controller와 worker에는 같은 충분히 긴 `WORKER_TOKEN`을, controller에는 24자 이상의 `APP_SESSION_SECRET`, 16자 이상의 `APP_ACCESS_TOKEN`, evaluator 결과 반영용 `OFFLINE_VERIFICATION_TOKEN`을 설정한다. 브라우저에는 `APP_ACCESS_TOKEN`만 입력하며 worker token과 OpenAI 키는 노출하지 않는다. target과 worker에 동일한 `LAB_USER_A_PASSWORD`, `LAB_USER_B_PASSWORD`, `LAB_ADMIN_PASSWORD`를 설정한다. 이미 seed한 DB의 비밀번호를 바꿀 때는 target DB를 제거해 재-seed해야 하며 일반 reset은 문서 fixture를 보존한다.

`.env`는 자동으로 로드하지 않는다. VM별 환경 파일 분리와 PowerShell/Linux 로딩 명령은 [`docs/environment_loading.md`](docs/environment_loading.md)에 있다.

controller는 발급한 세션 nonce의 SHA-256 해시·만료·철회 상태만 controller SQLite에 저장한다. 같은 DB와 `APP_SESSION_SECRET`으로 재시작하면 로그아웃한 세션은 계속 거부되고, 로그아웃하지 않은 유효 세션은 만료 전까지 유지된다. 이 테이블 도입 전에 발급되어 DB 행이 없는 쿠키와 secret을 교체한 뒤의 쿠키는 무효다.

기본 provider는 `mock`이다. live 실행은 다음 값이 모두 있어야 한다.

```dotenv
MODEL_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=계정에서 실제 사용 가능한 명시적 모델 ID
```

live provider의 키·모델 권한·API 호출이 실패하면 해당 run은 `FAILED`로 종료하며 mock으로 자동 전환하지 않는다.

OpenAI Agents SDK는 애플리케이션 안에서 실행되고 애플리케이션이 도구·상태·승인 경계를 소유하는 구조로 사용했다. 로컬 Streamable HTTP 연결은 Hosted MCP가 아니라 `MCPServerStreamableHttp`를 사용한다. 참고: [Agents SDK 개요](https://developers.openai.com/api/docs/guides/agents/sdk), [Agents SDK quickstart](https://developers.openai.com/api/docs/guides/agents/quickstart?lang=python), [MCP 안전 지침](https://developers.openai.com/api/docs/guides/tools-connectors-mcp).

## 실행

세 터미널 또는 세 VM에서 저장소 루트를 현재 디렉터리로 두고 실행한다. 아래의 `.env.*` 파일은 `docs/environment_loading.md`에 따라 만들며 커밋하지 않는다.

```powershell
# target VM
.\.venv\Scripts\python.exe -m uvicorn target.app:app --env-file .env.target --host 10.78.0.30 --port 8080

# worker VM
.\.venv\Scripts\python.exe -m uvicorn --factory worker.app:create_app_from_env --env-file .env.worker --host 10.77.0.20 --port 9000

# controller VM (frontend/dist가 먼저 빌드되어 있어야 함)
.\.venv\Scripts\python.exe -m uvicorn --factory controller.api:create_app_from_env --env-file .env.controller --host 192.168.56.10 --port 8000 --workers 1
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

controller DB/UI까지 정제된 최종 결과를 반영하려면 evaluator 위치에서만 `OFFLINE_VERIFICATION_TOKEN`을 읽어 다음 선택 인자를 사용한다. target DB나 원문은 전송하지 않고 결과·증거 identity digest만 전송한다. 이 토큰을 가진 evaluator는 최종 verdict·finding·warning을 제출하는 신뢰 운영 주체이므로 endpoint와 토큰은 격리망 또는 TLS 경계 안에서 제한한다.

```powershell
.\.venv\Scripts\python.exe -m verifier.cli evaluate --run-dir reports/runs/<run_id> --local-evidence <target.sqlite3 경로> --controller-url http://192.168.56.10:8000 --import-token $env:OFFLINE_VERIFICATION_TOKEN
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

테스트는 취약/수정/정상/없는 문서/로그인 오류, URL 정책, worker 인증, 정확히 N회인 HTTP 한도, gzip/deflate 단일 해제와 압축·해제 후 byte cap, rate-limit/semaphore/외부 task/진행 중 취소, controller 전체 timeout·queued 취소·재시작 후 세션 철회, verifier 위조 계정/run/문서/상관 플래그 거부, DB 재시작·redaction·이벤트 순서, UI 비동기 대화/run guard와 지연 terminal snapshot, 작업→SSE→보고서, loopback/등록 VM Host MCP 경계와 환경 프록시 차단을 포함한다. React 검증은 Node 상태 회귀 테스트와 소스 계약 검사이며 실제 브라우저 E2E 증거가 아니다. VM 방화벽·NIC 격리와 실제 OpenAI 모델 품질도 로컬 테스트에 포함되지 않는다.

자세한 구조와 운영 절차는 `docs/`와 `reports/evidence_index.md`를 본다.
