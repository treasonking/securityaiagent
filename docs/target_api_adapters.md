# 검사 대상 웹 API 어댑터

`codex/target-api-adapters`는 `codex/service-auth-config`의 `ac1e00f`에서 시작했다. 서비스별 환경 파일과 검증 launcher를 유지하면서, 검사 대상의 로그인·세션·리소스 구조를 운영자 JSON 설정으로 분리했다. 같은 `access-control-http` engine·worker·verifier를 function과 MCP가 공유한다. 검사 코드 수정 없이 아래 설정 쌍을 선택한다.

| 선택 | 기본 documents | 두 번째 records |
|---|---|---|
| worker `TARGET_REGISTRY_PATH` | `config/targets.json` | `config/targets.records.json` |
| target `TARGET_API_STYLE` | `documents` (기본) | `records` |
| Scope | `lab-access-control` r4 | `lab-records-access-control` r1 |
| 로그인 POST | `/login`, username/password | `/api/session`, login_name/passphrase |
| 인증 추출·전달 | `lab_session` 쿠키 → Cookie | `session.access_token` → Authorization: Bearer |
| 본인 목록 GET | `/documents`, documents | `/api/me/records`, data.items |
| 목록 ID / 소유자 | document_id / owner_id | key / owner.key |
| 상세 GET | `/documents/{document_id}` | `/api/records/{document_id}` |
| 상세 ID / 소유자 | document_id / owner_id | record.key / record.owner.key |
| 비공개 / 공개 | visibility: private / public | record.shared: false / true |
| 합성 내용 | canary.kind / canary.value | record.content.type / record.content.text |

두 설정 모두 등록된 `lab-web`, `http://10.78.0.30:8080`에 한정된다. 같은 VM/포트에서 하나씩 선택하며 임의 외부 사이트를 추가하는 기능이 아니다. `access-control`의 기존 target-log 판정은 정확한 기본 어댑터만 지원한다. records는 `access-control-http`만 허용한다.

## 설정 계약

전체 예시는 위 두 registry에 있다. `targets.lab-web.profile.http_routes`는 운영자가 승인한 경로이고, `targets.lab-web.adapter.routes`는 API 구조 설명이다. 둘이 다르면 worker 시작부터 `SCOPE_ADAPTER_MISMATCH`로 거절한다. 어댑터만 수정해 Scope를 확대할 수 없다. 로그인은 POST, 목록·상세는 GET으로 고정된다.

- `accounts.user_a/user_b/admin`에는 `username`과 `password_env`만 둔다. 비밀번호 참조는 기존 `LAB_USER_A_PASSWORD`, `LAB_USER_B_PASSWORD`, `LAB_ADMIN_PASSWORD` 중 서로 다른 이름이어야 한다. 실제 값은 worker/target 각자의 환경 파일에만 둔다. 세 참조 모두 시작 시 해석하며 누락 시 거절한다.
- `login_user_field`, `login_password_field`는 서로 다른 JSON 최상위 필드명이다. `auth_mode=cookie`는 `cookie_name`만, `auth_mode=bearer`는 `token_field`만 설정한다. Bearer의 `cookie_name`은 null이다. 후속 요청에 선택한 인증값만 전달하며 타 응답 쿠키를 복사하지 않는다.
- `identity_header`, `list_account_field`는 인증된 합성 계정 식별용이다. `list_field`, `list_id_field`, `list_owner_field`로 목록을, `resource_id_field`, `owner_field`, `visibility_field`로 상세를 정규화한다. 공개 여부는 타입까지 비교한다.
- `content_field`, `content_kind_field/value`, `content_container_field`는 합성 내용 계약이다. 원문은 worker 안에서만 처리하고 유효성·digest만 증거로 만든다. `denial_field/value`와 정확히 일치하는 오류 구조 및 인증된 응답 ID가 있어야 403/404를 리소스 거절 증거로 사용할 수 있다.
- JSON selector는 최대 6단계 객체 키 경로다. 배열 인덱스, wildcard, JSONPath, 정규식 실행, eval, 스크립트, 동적 URL은 지원하지 않는다. 목록 자체만 배열이며 최대 100개다. 경로는 길이 제한된 정규 literal 경로이며 상세의 마지막 `{document_id}`만 치환한다. 리소스 ID는 기존 `doc-[a-z]+-[0-9]{3}` 합성 형식을 유지한다.
- unknown 필드, JSON 중복 키, 잘못된 타입, URL authority/query/fragment/encoding/dot segment, 인증 방식 충돌을 거절한다. 응답 JSON 중복 키·비정상 구조도 판정 근거로 받지 않는다.

정규화한 전체 어댑터, 비밀값 **참조 이름**, Scope, origin, scenario, 실효 한도를 snapshot SHA-256에 포함한다. 비밀값 자체는 포함하지 않는다. 시작 시 로드한 registry와 run snapshot은 파일 변경에 영향을 받지 않으며 설정 반영에는 worker 재시작이 필요하다. 모든 실제 전송 직전에 method/path/origin과 계정·세션을 재검사한다. redirect는 따르지 않는다.

HTTP 시나리오의 9회 HTTP / 10회 도구 상한과 기존 rate/timeout/byte cap을 유지한다. 불완전 흐름·인증 실패·공개 리소스·모호한 응답은 `INCONCLUSIVE`다. worker 밖에는 비밀번호, 원문 토큰·쿠키, 원문 합성 내용이 전달되지 않는다. scope fingerprint는 신원 메타데이터이며 서명이 아니다.

기존 schema 2.0 파일에서 어댑터·경로를 생략하면 기본 documents 계약을 적용한다. 이번부터 hash에 어댑터가 포함되므로 종전 hash와 달라진다. 기본 프로필을 r4로 올렸으며 기존 r1~r3 및 사용자 VM 증거를 수정하거나 새 검증으로 간주하지 않는다.

## VM 업데이트

아래는 운영자 실행 절차이며 이번 작업에서 VM에 적용하지 않았다. 실행 중 run을 끝내고 각 서비스 소유 터미널에서 정상 종료한 뒤 같은 커밋으로 갱신한다. 다른 프로세스를 일괄 종료하거나 기존 DB·환경 파일을 삭제하지 않는다.

인터넷 연결된 저장소에서:

```bash
git fetch origin
git bundle create securityaiagent-adapters.bundle origin/codex/target-api-adapters
git bundle verify securityaiagent-adapters.bundle
git rev-parse origin/codex/target-api-adapters
```

bundle을 승인된 전달 경로로 세 VM의 저장소 루트에 복사한다. controller·worker·target **각 VM**에서:

```bash
git status --short
git bundle verify securityaiagent-adapters.bundle
git fetch ./securityaiagent-adapters.bundle refs/remotes/origin/codex/target-api-adapters:refs/remotes/origin/codex/target-api-adapters
git switch -c codex/target-api-adapters --track origin/codex/target-api-adapters
git rev-parse HEAD
```

작업 파일 변경이 있으면 먼저 보존한다. 이미 동일 로컬 브랜치가 있으면 `git switch codex/target-api-adapters` 후 `git merge --ff-only origin/codex/target-api-adapters`를 사용한다. 세 HEAD가 배포할 커밋과 일치해야 한다. 새 의존성은 추가하지 않았다. 기존 잠금 파일에 맞는 Python 3.12 venv를 유지한다.

### target VM

기존 `.env.target`에서 다음 키만 선택·반영하고 계정 비밀번호와 DB 경로는 유지한다.

```dotenv
TARGET_API_STYLE=records
TARGET_MODE=fixed
```

```bash
.venv/bin/python -m common.service_config check target --env-file .env.target
.venv/bin/python -m common.service_config serve target --env-file .env.target
```

기본 API는 `TARGET_API_STYLE=documents`, 취약 fixture는 `TARGET_MODE=vulnerable`이다. 각 변경마다 target을 정상 재시작한다. `serve`가 파일의 TARGET_MODE를 명시적으로 읽어 자식 프로세스에 전달하므로 부모 셸에 남은 모드를 사용하지 않는다. DB에 이미 저장된 계정 비밀번호는 환경 파일 수정만으로 바뀌지 않는다.

### worker VM

records 선택 시 기존 `.env.worker`에:

```dotenv
TARGET_REGISTRY_PATH=config/targets.records.json
TARGET_BASE_URL=http://10.78.0.30:8080
```

```bash
.venv/bin/python -m common.service_config check worker --env-file .env.worker
.venv/bin/python -m common.service_config serve worker --env-file .env.worker
```

documents 복귀 시 registry를 `config/targets.json`으로 바꾸고 재시작한다. `check` 출력의 profile/revision/hash/실효 한도를 보관한다. 네트워크 없이 구조를 확인할 때는 다음 명령으로 어댑터 ID·인증 방식·승인 경로를 볼 수 있다. 이 단독 명령은 `.env.worker`를 자동 로드하지 않으므로 실제 launcher의 실효 한도 확인은 반드시 위 `check worker` 출력으로 한다.

```bash
.venv/bin/python -m worker.cli check-policy --registry config/targets.records.json
```

### controller VM

환경 분리는 그대로 유지한다. `.env.controller`의 provider를 mock으로 유지하고 UI 빌드 후 실행한다.

```bash
cd frontend
npm run build
cd ..
.venv/bin/python -m common.service_config check controller --env-file .env.controller
.venv/bin/python -m common.service_config serve controller --env-file .env.controller
```

UI에서 `access-control-http`, `lab-web`, `mock`을 선택하고 function/MCP 각각 실행한다. CLI를 쓰려면 별도 서비스 전용의 깨끗한 셸에서 아래 명령을 사용한다. 직접 CLI는 launcher의 부모 환경 필터를 거치지 않는다.

```bash
.venv/bin/python -m dotenv -f .env.controller run -- .venv/bin/python -m controller.cli run --scenario access-control-http --target lab-web --provider mock --transport function
.venv/bin/python -m dotenv -f .env.controller run -- .venv/bin/python -m controller.cli run --scenario access-control-http --target lab-web --provider mock --transport mcp
```

documents/records 각각 vulnerable/fixed를 target VM에서 선택·재시작하여 총 8조합을 실행한다. 정상 기대값은 vulnerable=`VULNERABLE`, fixed=`BLOCKED_BY_ACCESS_CONTROL`, COMPLETED, 증거 7개, `http_observation`, 실제 HTTP 9회·도구 10회다. UI 정책 상한과 실제 사용량을 구분한다. controller에서 run ID와 `reports/runs/<run_id>/report.json`, `evidence.json`을 보관한다. target DB/log를 HTTP verifier에 입력하지 않는다.

controller VM에서 저장된 한 run을 재판정한다. 아래 `RUN_ID`를 해당 실행 ID로 바꾸고 각 실행마다 반복한다. 이는 저장된 정제 증거의 일관성 검사이며 새 HTTP 요청을 보내지 않는다.

```bash
.venv/bin/python - reports/runs/RUN_ID <<'PY'
import json, sys
from pathlib import Path
from common.schemas import Evidence
from verifier.http import verify_http_access_control
p = Path(sys.argv[1])
report = json.loads((p / 'report.json').read_text(encoding='utf-8'))
assert report['scenario_id'] == 'access-control-http'
evidence = [Evidence.model_validate(x) for x in json.loads((p / 'evidence.json').read_text(encoding='utf-8'))]
result = verify_http_access_control(evidence, run_id=report['run_id'])
print(json.dumps({'run_id': report['run_id'], 'status': report['status'],
    'verdict': result.verdict, 'verdict_matches': result.verdict == report['verdict'],
    'evidence_count': len(evidence), 'verification_basis': report['verification_basis'],
    'actual_usage': report['limits_used'], 'scope_policy': report.get('scope_policy')}, indent=2))
assert result.verdict == report['verdict']
PY
```

이 블록은 Bash 문법이다. Windows에서는 같은 Python 본문을 로컬 검증 파일로 저장한 뒤 `.\.venv\Scripts\python.exe <검증파일.py> reports/runs/<run_id>`로 실행한다. 사용자 제공 UI 출력과 controller 파일 재판정 결과의 출처를 별도 기록한다. 성공 판정만으로 VM NIC/방화벽이나 외부 사이트가 검증된 것은 아니다.

계정/한도 시험은 worker에서 선택 registry의 **별도 로컬 사본**을 만들어 각각 `profile.scenarios.access-control-http=["user-a"]` 또는 `profile.limits.max_requests=2`로 좁히고 `.env.worker`가 해당 사본을 가리키게 한 뒤 재시작한다. 두 API, 두 전송에서 실행하면 각각 `SCOPE_ACCOUNT_DENIED`(첫 user-a 로그인 1회 후 user-b 거절) / `SCOPE_LIMIT_EXCEEDED`(HTTP 2회 후 거절), `INCONCLUSIVE`가 기대값이다. 시험 후 원래 registry 경로 복원·worker 재시작을 확인한다. profile revision을 구분하고 실제 worker 반환 hash를 기록한다.

Windows VM에서는 `.venv/bin/python`을 `.\.venv\Scripts\python.exe`로 바꾼다. 전체 로컬 회귀와 격리된 TCP 행렬 재현은 저장소 루트에서:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m scripts.run_adapter_verification
```

이 스크립트의 loopback 임시 포트 허용은 테스트 코드 전용이다. 배포 registry에 복사하지 않는다. 실제 결과와 미검증 범위는 [어댑터 검증 보고서](../reports/api_adapter_verification.md)에 구분했다.
