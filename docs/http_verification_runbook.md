# 로컬 HTTP 관측 기반 접근 통제 검증

`access-control-http`는 등록된 `lab-web`과 `user-a`/`user-b`만 사용한다. 합성 문서 GET 외의 변경 도구는 없다. 로그인 POST는 worker가 기존 계정 설정으로 수행한다. 기본 provider는 `mock`이며 OpenAI 키가 필요 없다.

## 판정 계약과 호환성

두 로그인 → 두 자기 문서 목록 → A 상세 → B 상세 → A로 B 상세 → B 재조회 → A 재조회 → finish 순서다. 정상 완료는 **HTTP 9회, 도구 10회, 증거 7개**다. HTTP 시나리오는 기존 운영 한도와 각각 9/10 중 작은 값을 사용한다. 기존 시나리오의 전역 한도를 올리지 않는다.

타겟은 인증된 문서 응답에 `X-SecurityLab-Account`, 목록에 `account_id`와 문서별 `owner_id`, 상세에 `document_id`·`owner_id`·`visibility: private`·`canary: {kind: synthetic-private, value: ...}`를 제공한다. canary 형식은 `SYN-` 뒤 8~96개의 영문/숫자/밑줄/하이픈이다. 값이나 문서 ID의 정답은 verifier에 하드코딩하지 않는다. 문서 ID는 기존 `doc-[a-z]+-[0-9]{3}` 허용 형식을 유지한다.

worker는 계정 표시를 등록된 계정 참조로 변환하고, 문서 ID·소유 관계·세션 결합 해시·canary SHA-256·응답 종류·상태만 기록한다. 비밀번호, 실제 세션 쿠키, 상세 원문 및 canary 원문은 HTTP 보고서/모델에 전달하지 않는다. 불투명 세션 참조는 controller와 worker의 도구 호출에만 사용하며 모델·UI·보고서에 저장하지 않는다.

- `VULNERABLE`: 독립 계정 세션, 정상 소유자 목록/상세, 서로 다른 private canary, 동일 리소스 경로, 교차 응답의 소유자/문서/canary 일치, 두 계정 재조회가 모두 유효하다.
- `BLOCKED_BY_ACCESS_CONTROL`: 위 통제 조건과 인증 계정 표시가 유효하고, 동일 리소스의 교차 요청이 403/404 및 정확한 합성 문서 거절 구조이며 canary가 없다. 소유자 재조회도 성공해야 한다.
- `INCONCLUSIVE`: 로그인/공통 오류/공개 응답, 소유 관계 불명, 세션 실패, 구조 불일치, timeout, 전송/크기/예산 제한, 중복/다른 run/다른 계정/다른 리소스 증거, 통제 실패 등. 200 또는 전체 응답 해시 일치만으로 취약 판정을 하지 않는다.

`verifier/http.py`는 정제된 HTTP 증거와 기대 run ID만 입력받는다. target DB, observations, health/mode, 정답 fixture, 모델 후보를 읽지 않는다. HTTP 보고서 `mode`는 `unknown`, `verification_basis`는 `http_observation`, `environment.target_server_log`는 `not_used`다. 결과는 테스트 계정·리소스·시점에만 적용된다.

보고서 schema `1.1`은 `verification_basis`와 선택적 `Evidence.http_observation`을 추가한다. 기존 `1.0` JSON도 읽으며, 기준 필드가 없으면 기존 환경의 `correlated`/`offline-correlated`만 `target_log_correlated`로 읽고 나머지는 `pending_target_log`로 둔다. 기존 파일을 일괄 변환하지 않는다. 기존 증거의 digest 계산은 그대로이며 HTTP 증거는 새 메타데이터까지 포함한다.

`access-control`은 로그가 없으면 여전히 `INCONCLUSIVE`이며 기존 offline evaluator/import/digest/UI 새로고침을 사용한다. HTTP 결과에는 offline import를 적용할 수 없다(API 409, CLI 거절). UI는 실행 시 두 시나리오를 선택할 수 있으며, 결과의 기준에 따라 HTTP 안내 또는 기존 target-log 상태를 표시한다.

## Windows PowerShell: 독립된 로컬 네 조합

저장소 루트에서 Python 3.12와 Node.js 22를 사용한다. 가상환경이 이미 정상 설치되어 있으면 설치 단계는 생략한다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-full.lock
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe scripts/run_http_verification.py
```

스크립트는 사용자 서비스와 겹치지 않는 OS 할당 loopback 포트, 임시 DB, 무작위 worker 토큰을 사용한다. `config/targets.json`이나 배포 환경을 바꾸지 않는다. 자신이 기동한 target/worker만 종료하고 임시 DB를 정리한다. target 및 worker 모두 실제 TCP HTTP로 실행하며 function REST와 SDK Streamable HTTP MCP를 각각 사용한다. 임시 DB는 `verification_tmp/` 아래에만 생성한다.

`reports/http_verification/http-<uuid>/report.json`, `report.md`, `evidence.json`과 고유 `matrix-<uuid>.json`이 생성된다. 반복 실행은 새 run을 추가한다. 취약 × function/MCP는 `VULNERABLE`, 수정 × function/MCP는 `BLOCKED_BY_ACCESS_CONTROL`이어야 한다. 각 행은 증거 7개와 `http_observation` 기준을 표시한다. verifier에 주입한 DB reader는 호출 시 실패하도록 되어 있다. 판정 후 스크립트가 별도로 target 로그의 요청 identity·계정·canary 해시를 대조하며 원문/DB를 내보내지 않는다.

회귀 검증:

```powershell
New-Item -ItemType Directory -Force verification_tmp | Out-Null
$env:PYTEST_DEBUG_TEMPROOT = (Get-Item verification_tmp).FullName
$env:PYTEST_ADDOPTS = '-o cache_dir=verification_tmp/pytest-cache'
.\.venv\Scripts\python.exe -m pytest
Push-Location frontend
npm ci
npm test
npm run build
Pop-Location
```

`PYTEST_DEBUG_TEMPROOT`/cache 설정은 기존 Windows 임시 폴더 ACL 충돌을 피하기 위한 로컬 설정이다. 보안 정책이나 네트워크 권한을 완화하지 않는다.

## Ubuntu: 동일한 로컬 재현 명령

아래 명령은 제공하지만 이번 Windows 실행에서 Ubuntu/VM 실행을 검증한 것은 아니다.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-full.lock
.venv/bin/python scripts/run_http_verification.py
.venv/bin/python -m pytest
(cd frontend && npm ci && npm test && npm run build)
```

## 기존 VM에서 재검증할 명령

target/worker/controller를 동일한 수정 버전으로 갱신하고, 각 VM에서 기존 전용 환경 파일과 등록 네트워크 설정을 사용한다. [환경 로딩 가이드](environment_loading.md)에 따라 target 및 worker 서비스를 직접 운영한다. NIC/MAC/방화벽/RAM/CPU는 변경하지 않는다. 기존 보존 DB를 삭제하지 않는다.

각 target 모드(`vulnerable`, `fixed`)에서 아래 두 명령을 실행하면 네 조합이 된다. 모드는 target 운영자가 `.env.target`에서 설정하고 자신이 관리하는 target을 재시작한다. HTTP verifier는 이 모드 값을 받지 않는다. worker에는 계정 비밀번호가 필요하지만 controller에는 `WORKER_TOKEN`, `WORKER_URL`, `MCP_WORKER_URL`만 필요하다. `.env.controller`는 기존 가이드로 현재 터미널에 로드하거나 아래 dotenv 실행을 사용한다.

```powershell
.\.venv\Scripts\python.exe -m dotenv -f .env.controller run -- .\.venv\Scripts\python.exe -m controller.cli run --scenario access-control-http --target lab-web --provider mock --transport function
.\.venv\Scripts\python.exe -m dotenv -f .env.controller run -- .\.venv\Scripts\python.exe -m controller.cli run --scenario access-control-http --target lab-web --provider mock --transport mcp
```

```bash
.venv/bin/python -m dotenv -f .env.controller run -- .venv/bin/python -m controller.cli run --scenario access-control-http --target lab-web --provider mock --transport function
.venv/bin/python -m dotenv -f .env.controller run -- .venv/bin/python -m controller.cli run --scenario access-control-http --target lab-web --provider mock --transport mcp
```

CLI 결과는 `reports/runs/<run_id>/`에 기록된다. UI 이력에 남기려면 UI에서 `access-control-http`와 transport를 선택해 실행한다. HTTP 결과에는 offline import가 필요 없다. CLI `COMPLETED`만 보지 말고 verdict/basis/증거 수/경고를 확인한다. 판정이 `INCONCLUSIVE`이면 CLI 종료 코드는 1이다.

## 실패 확인과 한계

- `No Python at ...`: `.venv/pyvenv.cfg`가 삭제된 Python을 가리키는지 확인하고 설치된 Python 3.12로 가상환경을 복구한다.
- 인증·소유 관계 실패: target/worker 버전과 비밀번호 설정, 목록·상세 계정 표시, 실제 세션 유효성을 확인한다. 오래된 target에는 HTTP 전용 메타데이터가 없으므로 판정을 확정하지 않는다.
- 예산 초과: 정상 요청 9회/도구 10회를 허용하는지 확인한다. 에이전트가 임의로 한도를 늘리지는 않는다.
- MCP 연결 실패: 기존 worker 토큰, 등록 Host/Origin/client allowlist를 확인한다. 전체 호스트 허용이나 임의 외부 URL 입력으로 우회하지 않는다.
- 리다이렉트: 내부/외부 모두 따라가지 않는다. 원래 등록된 정규화 문서 경로에서 반환되는 응답을 사용한다.
- Windows 임시 DB 정리 실패: 이 버전은 target SQLite 연결을 명시적으로 종료한다. 실패한 실행은 성공으로 덮어쓰지 말고 run ID와 오류를 함께 남긴다.

OpenAI 실호출, VM 네 조합, 실제 브라우저 E2E, 외부 웹사이트, Nmap/Playwright, 자동 제보 및 모델 학습은 이번 검증에 포함되지 않는다. 외부 적용 전에는 별도의 프로그램 허용 범위·계정·요청 한도 정책 설계가 필요하다.
