# 독립 로컬 첨부파일 API 적용성 검증

이 실험은 **구현자가 구조를 알고 어댑터를 작성한 내부 적용성 검증**이다. 블라인드 평가, 외부 사이트 일반화 성능, 실전 버그 바운티 검증이 아니다. 등록된 두 계정·두 비공개 리소스를 기존 `operator-resource-http` 계약에 연결한다. 모델 provider는 mock이며 유료 API를 호출하지 않는다.

시작 시 PR #1은 미병합이었다. 원격 main `17d72b8`, 검토 완료 `4f637f58142b967aca0986d2ffc83b537ce9c4db`를 확인하고 후자에서 `codex/independent-api-validation`을 만들었다. 기존 VM/환경파일/DB/방화벽/공유 폴더나 운영 registry는 변경하지 않는다.

## 1. 기존 엔진 변경 없이 설정한 부분

`validation/independent_api/registry.cookie.json`과 두 OpenAPI 문서에 API의 실제 구조를 명시한다. `configuration.py`는 실행 시 자신이 확보한 loopback port와 선택한 cookie/Bearer 방식만 바꾸며, 예산 음성 대조에서만 max_requests=2로 낮춘다. 운영 `config/targets*.json`을 로드하거나 수정하지 않는다.

| 구분 | 독립 첨부파일 API 매핑 |
|---|---|
| 로그인 | `POST /gateway/authenticate`, `handle` / `secret` |
| 로그인 이름 / principal | `cedar_editor` → `member_K73`, `quartz_reviewer` → `member_R92` |
| 본인 확인 | `GET /gateway/session/profile`, `context.member.subject` |
| 첨부파일 | `GET /workspace/attachments/{resource_id}`, `attachment_M4s8` / `attachment_N9t2` |
| ID / 소유자 | `artifact.key` / `artifact.acl.holder` |
| 가시성 | `artifact.acl.classification`, private=`restricted`, public=`shared` |
| 합성 proof | `content.audit.receipt` |
| 명시적 거절 | HTTP 403, 정확한 객체 `{"problem":{"kind":"attachment_forbidden"}}` |
| cookie | `project_sid` |
| Bearer | 로그인 응답 `session.grant.credential` |

기존 `common.operator_contract`, importer, Controller preview/run, Worker 및 verifier에 첨부파일 이름/경로를 위한 분기를 추가하지 않는다. target ID `lab-web`, 논리 별칭 `user-a`/`user-b`, 네 secret reference 이름은 **기존 계약이 고정한 별칭**으로 유지한다. 서버의 로그인 이름/principal/리소스 ID는 이 별칭과 다르다.

## 2. 추가 코드와 독립성

- `validation/independent_api/api.py`: Python 표준 라이브러리 `ThreadingHTTPServer`와 별도 Member/Attachment 모델, 프로젝트 구성원 권한 검사, 메모리 세션 저장소를 구현한다. 기존 FastAPI fixture, `target.app`, TargetStore, canary helper를 import·상속·복제하지 않는다. API는 agent registry/별칭/계약/verifier를 모른다.
- 취약 모드는 프로젝트 구성원 검사를 생략하고, 수정 모드는 소유자 접근을 유지하면서 교차 계정을 403으로 거절한다. 구현 모드와 기대 판정은 harness/서버에서만 사용하며 verifier에 전달하지 않는다.
- `transport.py`: 이번 테스트가 생성한 Worker의 실제 loopback uvicorn listener 수명만 관리한다. 정책 변경 시험에서만 자신의 이전 port로 새 Worker를 시작한다.
- `scripts/run_independent_api_validation.py`: 기존 preview, 계획 파일 검토, 명시적 digest run, issued/claimed 보존 및 저장 증거 replay를 연결한다. 소켓 transport 대체나 ASGI 직접 호출을 사용하지 않는다. 증거 회수/비밀값 검사/계수는 verifier 외부에 둔다.
- `tests/test_independent_api.py`: 실제 TCP 행렬, 잘못된 digest·단일 사용 이력, 비밀값 유출 시 공개 전 중단, 어댑터 불일치 및 지원하지 않는 구조를 검증한다.

추가 코드는 대상 구현·설정·검증 harness에 한정된다. 엔진 재설계나 v1 계약 확장은 필요하지 않았다. AGENTS.md에는 이 패키지와 스크립트의 임시 loopback 합성 테스트에 한한 좁은 예외만 추가한다.

## 3. 재현 및 TCP 측정 경계

저장소 루트의 기존 개발 venv와 의존성을 사용한다. 외부 URL, 계정 비밀, port, shell 명령을 인자로 받지 않는다. output은 존재하지 않는 새 폴더여야 한다.

```powershell
.\.venv\Scripts\python.exe -m scripts.run_independent_api_validation --output verification_tmp/independent-attachments-new
.\.venv\Scripts\python.exe -m pytest tests/test_independent_api.py
.\.venv\Scripts\python.exe -m pytest
```

frontend 디렉터리에서 `npm run build`를 실행한다. 실제 실행·검증 수치는 [2026-11-13 정제 결과](../reports/independent_api_validation_20261113/README.md)에 기록한다.

정상 행렬은 취약/수정 × cookie/Bearer × function/MCP의 8건이다. 모든 실행은 새 비밀번호·proof·세션·Worker token과 별도 target/Worker TCP listener를 갖는다. function은 실제 REST 요청, MCP는 실제 Streamable HTTP handshake/tool 요청이다. Worker 수신 계수도 두 전송을 구분해 남긴다.

preview 전후 API HTTP handler 진입 계수의 차이를 비교한다. 정상 run은 API 수신 11회, Worker HTTP 11회·도구 12회, 저장 증거 11개와 재판정 일치를 요구한다. 두 정책 조회는 Target 요청/도구 사용량에 포함하지 않으며 MCP handshake 등 transport 제어도 도구 12회와 구분한다. Target health를 별도로 호출하지 않아 preview 시작 계수는 0이고, 후속 run의 11회가 같은 계수기의 양성 대조가 된다. TCP 패킷 캡처라고 주장하지 않는다.

## 4. 실패 조건의 차단 시점

각 조건은 cookie/function과 cookie/MCP에서 실행한다. 조건별 기대값은 판정과 별도로 harness에서 비교하며 결과에 맞춰 바꾸지 않는다.

| 조건 | 검사 경계 | 대상 요청 기준 |
|---|---|---|
| preview 후 정책 변경 | preview Worker 종료 → 새 proof commitment의 Worker로 같은 port 재시작 → Controller run 정책 재조회에서 거절 | 0, 첫 로그인·claim 전에 중단 |
| 예산 2회 | Worker가 세 번째 HTTP 요청 전에 예산 검사 | 최대 2, INCONCLUSIVE |
| 소유자 불일치 | 첫 소유자 응답부터 다른 등록 principal을 반환; 전체 관찰 후 verifier가 소유자 대조를 불인정 | 11, INCONCLUSIVE |
| proof 재조회 변경 | 정상 소유자 두 번째 조회(전체 8·9번째 요청)에서 새 합성 proof 반환; verifier가 안정된 소유자 대조를 불인정 | 11, INCONCLUSIVE |

정책 거절은 실행 자체가 시작되지 않아 run ID/report/replay/claimed가 없으며 null로 기록한다. 이를 성공한 MCP 도구 실행이나 verifier의 INCONCLUSIVE 판정으로 꾸미지 않는다. 정책 검사는 두 전송 모두 기존 REST 제어 경로다. issued plan·검토 기록·변경 전후 snapshot·0회 계수는 보존한다. 정책 조회와 첫 로그인 **사이**의 추가 race 주입은 이번 행렬의 정책 재시작 사례와 다르며 별도 검증 범위다.

proof 변경은 Worker에 등록한 기대 합성값과 매칭되지 않으므로 `OWNER_RESOURCE_PROOF_UNPROVEN`으로 거절될 수 있다. 반드시 `PROOF_NOT_STABLE_OR_DISTINCT`라는 특정 뒤쪽 reason을 요구하지 않는다. 상태/실제 reason/증거와 어느 재조회에서 변경했는지는 결과에 남긴다.

## 5. 증거·비밀값·보존

case별 catalogue/OpenAPI/registry, plan 및 검토 기록, issued/claimed, 실행 연결, report/evidence/verification_contract, replay와 result를 보존한다. `target_measurement.json`은 operation/status/수신 횟수만 포함하고 run 디렉터리 밖에 둔다. verifier는 기존의 정제 evidence와 policy, run ID만 받으며 target 내부 모델·모드·원본 응답·계수·기대 verdict를 읽지 않는다.

비밀번호, 초기·재조회 proof, 발급한 모든 cookie/Bearer token, Worker token 및 정책 변경 proof는 메모리에서 추적한다. 임시 staging의 공개 후보 전체를 해당 비밀값과 대조한 후에만 output에 복사한다. 발견하면 공개를 중단한다. 공개 파일에는 raw 응답이나 credential을 저장하지 않는다. 정책 commitment와 run별 proof digest는 허용된 계약 메타데이터다. 비밀 파일이나 기존 DB는 만들지 않는다. 이전 보고서는 덮어쓰지 않는다.

## 6. 여전히 제한되는 구조와 다음 범위

이 결과는 **한 종류의 새 JSON API가 설정만으로 연결되는지**를 검증한다. 계약은 여전히 다음에 종속된다.

- HTTP IP literal origin, 고정 JSON 로그인 두 필드와 정상 identity endpoint, cookie 또는 Bearer만 지원한다. HTTPS/DNS/SSO/OAuth 갱신/CSRF 다단계 로그인은 이번 범위 밖이다.
- 정확히 두 계정/두 리소스, 문자열 ASCII opaque ID, 마지막 하나의 `{resource_id}`만 허용한다. `/projects/{project_id}/attachments/{resource_id}` 같은 다중 동적 경로는 표현할 수 없어 고정 attachment lookup을 사용했다. 배열/JSONPath/스크립트 selector도 불가하다.
- object-key 중첩 selector는 최대 6단계다. 응답의 ID/owner/visibility/proof와 정상 identity를 명시적으로 등록해야 한다. 일반 바이너리 첨부파일이나 임의 HTML 의미를 평가하지 않는다.
- proof는 운영자가 사전에 준비한 고엔트로피 합성값이며, 정확한 403/404 거절 객체와 안정된 소유자 대조가 필요하다. 응답 구조를 모르는 상태의 자동 추론·탐색이 아니다.
- 고정 11 HTTP/12-tool 흐름은 A→B 교차 접근 하나를 검증한다. 임의 리소스 열거, 역방향 B→A, 모든 프로젝트/권한 조합의 포괄 검사는 아니다.
- importer는 일부 schema enum/const/pattern/format/복합 타입을 지원 증명으로 인정하지 않는다. 이번 명세는 지원되는 required object/string 구조로 기술했다. 이는 API 권한 자체가 아니라 importer의 표현 제약이다.

VM 적용·인터넷 차단 확인·UI 실제 브라우저·유료 모델·외부 버그 바운티 서비스 검증을 수행하지 않는다. 다음에는 독립 구현자가 제공한 고정 계약 내 API로 재현하고, 다중 경로/배열 등 필요한 계약 확장은 별도 설계·거절 회귀·권한 검토 후 판단하는 것이 적절하다.
