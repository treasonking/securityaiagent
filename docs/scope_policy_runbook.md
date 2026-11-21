# 실행 범위 정책 운영 가이드

이 기능은 등록된 합성 `lab-web`과 두 접근 통제 시나리오에만 적용한다. 일반 사이트 HTML·로그인 어댑터, 외부 프로그램 정책, Nmap/Playwright는 구현하지 않았다. `access-control`의 로그 대조와 `access-control-http`의 HTTP 관측 판정은 그대로 구분한다.

## 설정과 적용 시점

실제 설정 및 비밀 없는 예제는 [`config/targets.json`](../config/targets.json) 하나다. schema `2.0`, `targets.lab-web.origin=http://10.78.0.30:8080`과 `profile`을 포함한다. origin을 profile에 중복 정의하지 않는다. `TARGET_REGISTRY_PATH`는 운영자가 지정하는 로컬 파일 경로이며 채팅/API 입력이 아니다. 비밀번호는 기존 worker 환경 변수에만 둔다.

| profile 필드 | 현재 값 / 계약 |
|---|---|
| profile_id / revision / enabled | `lab-access-control` / `1` / `true`; revision은 변경 시 운영자가 증가 |
| scenarios | `access-control`: user-a/user-b/admin; `access-control-http`: user-a/user-b |
| operations | `login`, `list_own_documents`, `fetch_document` |
| limits | 아래 표의 모든 필드 필수 |

| limit 필드 | 프로필 기본 | HTTP 시나리오 실효 기본 | 전역 환경 변수 |
|---|---:|---:|---|
| max_requests | 30 | 9 | HTTP_MAX_REQUESTS |
| max_tool_calls | 12 | 10 | AGENT_MAX_STEPS |
| timeout_seconds | 5 | 5 | HTTP_TIMEOUT_SECONDS |
| run_timeout_seconds | 180 | 180 | RUN_TIMEOUT_SECONDS |
| max_response_bytes | 65536 | 65536 | HTTP_MAX_RESPONSE_BYTES |
| requests_per_second | 2 | 2 | HTTP_REQUESTS_PER_SECOND |
| max_concurrency | 1 | 1 | HTTP_MAX_CONCURRENCY |
| max_runs | 100 | 100 | WORKER_MAX_RUNS |
| state_ttl_seconds | 600 | 600 | WORKER_STATE_TTL_SECONDS |

모든 실효값은 전역·프로필·시나리오 상한 중 최솟값이다. 전역 속도 `0`은 기존의 “전역 속도 상한 없음” 뜻을 유지하지만 **양수 프로필 속도는 계속 적용**한다. 프로필의 0, 음수, bool 숫자, NaN/Infinity, 숫자 문자열, 정수 필드의 소수는 거절한다. 속도는 기존처럼 run별 요청 간격, 동시성은 worker 프로세스 전체, max_runs는 보존 중 run 상태 수, TTL은 종료/실패/취소 상태의 보존 시간이다. 다중 worker 프로세스 전체의 분산 한도는 아니다.

unknown 필드/enum, 중복 JSON 키/배열값, 누락 필드, 비활성 프로필은 자동 fallback 없이 실패한다. `TARGET_BASE_URL`을 설정했다면 등록 origin과 정확히 같아야 한다. DNS/wildcard/자격 증명/경로가 든 origin을 허용하지 않으며 기존 HTTP/IP literal 경계를 유지한다.

worker 시작 시 전체 설정을 검증해 메모리에 고정한다. **파일을 바꿔도 실행 중 run과 같은 프로세스의 신규 run 모두 기존 설정을 사용한다.** 새 정책은 worker 재시작 후의 run부터 적용된다. 진행 중 run은 UI의 기존 취소 기능으로 취소하고 재시작한다. 재시작 전 실행을 계속 이어가는 기능은 없다.

각 run은 계정·작업·origin·실효 한도의 불변 snapshot을 갖는다. 세션 생성 전, rate/semaphore 대기 후, HTTP stream 시작 직전에 동일 경로로 검사한다. 로그인은 worker 소유 자격 증명의 `POST /login`, 목록은 `GET /documents`, 상세는 정규화된 `GET /documents/doc-…-…`만 가능하다. 상세 ID는 기존 합성 fixture 형식을 사용한다. `finish_run`은 HTTP 로그아웃을 보내지 않고 상태를 봉인하고 쿠키를 제거한다. redirect를 따라가지 않는다.

## 오프라인 검사 — target 요청 없음

저장소 루트에서 실행한다. 운영 환경의 실효 한도를 보려면 worker와 같은 환경 파일을 명시적으로 로드한다.

```powershell
.\.venv\Scripts\python.exe -m worker.cli check-policy
.\.venv\Scripts\python.exe -m dotenv -f .env.worker run -- .\.venv\Scripts\python.exe -m worker.cli check-policy
```

```bash
.venv/bin/python -m worker.cli check-policy
.venv/bin/python -m dotenv -f .env.worker run -- .venv/bin/python -m worker.cli check-policy
```

기본은 `config/targets.json`이며 `--registry LOCAL_PATH`로 별도 운영자 파일을 검사할 수 있다. 성공 exit 0은 대상·시나리오·계정 참조·작업·실효 한도·fingerprint를 출력한다. 실패 exit 2는 정제된 reason code만 출력한다. 검사 성공은 VM 연결이나 자격 증명 성공을 의미하지 않는다.

## 거절과 보고서

| reason code | 의미 / 기대 전송 |
|---|---|
| SCOPE_INVALID / SCOPE_DISABLED | 정책/전역 한도 오류 또는 비활성; 시작 실패, HTTP 0 |
| SCOPE_ORIGIN_MISMATCH / SCOPE_TARGET_DENIED | origin 또는 등록 대상 불일치; 거절한 요청 0 |
| SCOPE_SCENARIO_DENIED / SCOPE_ACCOUNT_DENIED / SCOPE_OPERATION_DENIED | 허용 범위 밖; 거절한 요청 0 |
| SCOPE_PATH_DENIED / SCOPE_SESSION_DENIED | method/path 또는 run/account/session 결합 불일치; 거절한 요청 0 |
| SCOPE_LIMIT_EXCEEDED | 한도 도달; HTTP 횟수 N이면 N+1 전송 0. 응답 크기/시간 초과는 이미 시작한 전송을 중단 |
| SCOPE_RUN_FAILED | 이전 실패가 있는 run 재사용 거절 |
| SCOPE_METADATA_MISSING / SCOPE_SNAPSHOT_MISMATCH | controller가 worker 정책 정보 누락/변경 감지; 미완료 INCONCLUSIVE |

전송 전 거절과 이미 시작한 요청의 응답/시간 실패를 구분한다. 모든 정책 실패는 실행을 확정 취약/차단으로 바꾸지 않는다. 정제된 도구 이벤트·경고에 이유가 남으며 미완료는 `INCONCLUSIVE`다. 기존 취소/일반 경로 오류는 `POLICY_REJECTED`, 일반 전송 예외는 정제된 `TOOL_ERROR`를 유지한다.

새 report schema `1.2`의 `scope_policy`와 worker finish 결과는 실제 ID/revision/SHA-256/실효 한도를 포함한다. controller에는 별도 정책 사본이 없고 worker 반환값의 run 내 일관성을 확인한다. 해시는 정렬된 전체 프로필·schema·target ID·origin·scenario·실효 한도의 canonical JSON을 대상으로 하며 서명, 권한 부여 증명, 위조 방지 기능이 아니다. 임시 loopback 포트가 바뀌면 해시도 바뀐다. 구형 JSON 1.0/1.1은 계속 읽으며 없던 해시를 생성하지 않는다. UI는 읽기 전용이다.

## Windows 로컬 재현

다음 명령은 이번 개발에서 실행한 종류의 검사다. 네 조합 스크립트는 자신이 예약한 loopback 소켓/임시 DB만 사용한다. `run_matrix`의 output 인자로 과거 실행과 다른 폴더에 기록한다.

```powershell
New-Item -ItemType Directory -Force verification_tmp | Out-Null
$env:PYTHONUTF8 = '1'
$env:PYTEST_DEBUG_TEMPROOT = (Get-Item verification_tmp).FullName
$env:PYTEST_ADDOPTS = '-o cache_dir=verification_tmp/pytest-cache'
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -c "from pathlib import Path; from scripts.run_http_verification import run_matrix; run_matrix(Path('reports/scope_policy'))"
Push-Location frontend
npm test
npm run build
Pop-Location
git diff --check
```

Ubuntu 로컬 시험은 `.venv/bin/python -m pytest`, `.venv/bin/python -c "from pathlib import Path; from scripts.run_http_verification import run_matrix; run_matrix(Path('reports/scope_policy'))"`, `(cd frontend && npm test && npm run build)`이다. 이번 작업에서 Ubuntu/VM/실제 브라우저 시험은 실행하지 않았다.

## VM 전달·재시작 — 사용자가 다음에 실행할 절차

적용 버전은 `codex/scope-policy`의 [검증 보고서](../reports/scope_policy_verification.md)에 기록된 구현 커밋 이상이다. 개별 파일만 복사하지 말고 공통 schema·worker·controller·frontend·config가 같은 브랜치 상태인지 각 VM의 `git rev-parse HEAD`로 기록한다. `.env.*`와 DB는 Git bundle에 포함하지 않는다. 기존 파일/사용자 수정이 있으면 보존하고 충돌을 해결한다.

인터넷이 있는 Windows 개발 저장소에서 최종 커밋 후:

```powershell
git status --short
git rev-parse codex/scope-policy
git bundle create securityai-scope-policy.bundle codex/scope-policy
git bundle verify securityai-scope-policy.bundle
Get-FileHash -Algorithm SHA256 securityai-scope-policy.bundle
```

승인된 오프라인 전달 방식으로 bundle을 각 VM에 복사한 후 Ubuntu 저장소에서:

```bash
sha256sum securityai-scope-policy.bundle
git bundle verify securityai-scope-policy.bundle
git status --short
git fetch ./securityai-scope-policy.bundle refs/heads/codex/scope-policy:refs/remotes/bundle/scope-policy
git switch -c codex/scope-policy --track bundle/scope-policy
git rev-parse HEAD
```

이미 브랜치가 있으면 `git switch codex/scope-policy` 후 `git merge --ff-only bundle/scope-policy`를 사용한다. fast-forward가 불가하면 원인을 확인하며 강제 reset하지 않는다. DNS/방화벽/NIC/MAC/자원 설정은 바꾸지 않는다.

worker: schema 2.0 `config/targets.json`, `worker/{registry,scope,limits,service,cli,app}.py`, `common/schemas.py`를 포함한 같은 커밋을 적용하고 오프라인 검사 후 운영자가 관리하는 worker를 정상 종료·재시작한다.

```bash
.venv/bin/python -m dotenv -f .env.worker run -- .venv/bin/python -m worker.cli check-policy
.venv/bin/python -m uvicorn --factory worker.app:create_app_from_env --env-file .env.worker --host 10.77.0.20 --port 9000
```

controller: 공통 schema/engine/reporting과 frontend를 적용한다. `(cd frontend && npm ci && npm test && npm run build)` 후 controller를 정상 재시작한다. worker를 먼저 갱신해야 과거 구버전 422 또는 정책 metadata 누락을 피할 수 있다.

```bash
.venv/bin/python -m uvicorn --factory controller.api:create_app_from_env --env-file .env.controller --host 192.168.56.10 --port 8000 --workers 1
```

target: 이번 정책 변경 자체로 target 동작은 바뀌지 않는다. 이전 HTTP 합성 계약 구현이 있어야 하므로 커밋은 확인한다. vulnerable/fixed 모드를 바꿀 때는 보존할 DB를 삭제하지 않고 기존 모드별 `TARGET_DATABASE_PATH`와 `.env.target`의 `TARGET_MODE`를 명시적으로 로드해 운영자가 관리하는 target을 재시작한다.

```bash
.venv/bin/python -m uvicorn target.app:app --env-file .env.target --host 10.78.0.30 --port 8080
```

Windows VM의 재시작 명령은 같은 모듈/인자에 `.venv/bin/python` 대신 `.\.venv\Scripts\python.exe`를 사용한다. 과거 사용자 보고 422·bundle 전달·모드 로드 이력은 [HTTP 결과](../reports/http_verification_results.md)에 보존했다. 위 명령은 이번에 VM에서 실행한 증거가 아니다.

## 다음 VM 확인: 허용·거절·한도

1. 기본 프로필에서 각 target 모드별 controller mock function/MCP를 실행한다:

   ```bash
   .venv/bin/python -m dotenv -f .env.controller run -- .venv/bin/python -m controller.cli run --scenario access-control-http --target lab-web --provider mock --transport function
   .venv/bin/python -m dotenv -f .env.controller run -- .venv/bin/python -m controller.cli run --scenario access-control-http --target lab-web --provider mock --transport mcp
   ```

   예상: vulnerable 두 run `VULNERABLE`, fixed 두 run `BLOCKED_BY_ACCESS_CONTROL`, 증거 7개·HTTP 9회·도구 10회·`http_observation`. CLI 보고서는 `reports/runs/<run_id>/`에 기록된다.
2. 운영자 파일의 복사본에서 HTTP 시나리오의 `user-b`만 제외하고 revision을 올린다. `TARGET_REGISTRY_PATH`를 그 로컬 파일로 지정·검사·worker 재시작 후 위 mock 실행을 반복한다. 예상: A 로그인 1회 뒤 B 로그인은 전송 0, `SCOPE_ACCOUNT_DENIED`, `INCONCLUSIVE`. 사전 전체 거절은 HTTP 시나리오를 제거한 복사본으로 확인하면 target 요청 0이다.
3. 별도 복사본의 `max_requests=2`로 검사·재시작 후 반복한다. 예상: 로그인 2회 후 목록 N+1 요청 0, `SCOPE_LIMIT_EXCEEDED`, `INCONCLUSIVE`. request_count와 정책 snapshot을 함께 보존한다.

시험 후 원래 프로필/환경 경로를 복원하고 worker를 재시작한다. raw target 로그/DB는 target/evaluator 경계에 두고 정제된 실행 결과만 전달한다. 2026-10-20 작성 시점에는 새 정책의 VM 동작·실제 브라우저 레이아웃·외부 사이트 적용이 미검증이었다. 2026-10-22 사용자 보고로 확인된 VM 범위와 남은 한계는 아래 보완 절과 결과 문서에서 구분한다. OpenAI 추가 호출은 이 절차에 없다.

## 2026-10-22 사용자 보고 명령과 복원 주의

사용자 제공 지침에 실제 사용한 것으로 기록된 명령이다. 이 문서를 편집한 Codex가 VM에서 실행한 명령은 아니다. 인터넷 격리 worker는 Windows git bundle을 공유 폴더로 받아 scope 브랜치를 갱신했다. 구버전의 `No module named worker.cli`는 갱신 후 해소되고 `check-policy`가 성공했다고 보고됐다. 전역 Python/venv 재생성이나 DNS 변경은 하지 않았다.

검사와 기동에 같은 환경을 로드하고 프로세스별 정책 경로를 명시했다:

```bash
cd ~/securityaiagent
set -a
source ./.env.worker
set +a

TARGET_REGISTRY_PATH=verification_tmp/scope-deny-user-b.json \
  .venv/bin/python -m worker.cli check-policy

TARGET_REGISTRY_PATH=verification_tmp/scope-deny-user-b.json \
  .venv/bin/python -m uvicorn --factory worker.app:create_app_from_env \
  --env-file .env.worker --host 10.77.0.20 --port 9000
```

한도 시험에서는 경로만 `verification_tmp/scope-limit-two.json`으로 바꿨다. r2는 원본 정책 복사본의 HTTP 계정만 `[user-a]`, r3는 원본 정책의 별도 복사본에서 두 계정 허용과 `max_requests=2`를 적용했다. 정책 변경마다 worker를 Ctrl+C로 정상 종료한 후 재기동했다. 파일만 변경해도 실행 중 worker가 자동 갱신되는 것은 아니다.

아래는 시험 종료 후 원본 정책으로 돌아가기 위한 명령이다. **복원 완료를 확인한 출력은 아직 제공되지 않았다.** 같은 `.env.worker`를 로드한 터미널에서 현재 시험용 worker를 정상 종료한 뒤 원본 정책을 명시하여 시작하고, 실제 적용 profile/revision/hash를 확인한다.

```bash
TARGET_REGISTRY_PATH=config/targets.json \
  .venv/bin/python -m uvicorn --factory worker.app:create_app_from_env \
  --env-file .env.worker --host 10.77.0.20 --port 9000
```

여섯 run의 계수·해시·정제된 실패 이유와 확인 수준은 [VM 결과 기록](../reports/scope_policy_verification.md#사용자-제공-vm-scope-정책-6건--2026-10-22-기록)에 있다. HTTP 계수는 worker 보고값이며 패킷/target 로그 독립 대조는 아니다. 새 scope의 fixed 정상 두 조합과 복원 확인은 후속 작업으로 남긴다.
