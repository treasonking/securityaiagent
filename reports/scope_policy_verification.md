# Scope profile 로컬 검증 — 2026-10-20

## 적용 여부와 코드 기준

작업 시작 시 기존 exact-origin·경로·요청 예산 제어는 있었지만 운영자 scope profile, 불변 snapshot, 오프라인 정책 검사, 정책 metadata 보고는 없었다. 이 문서의 검증은 그 미구현 부분을 적용한 결과다.

- 저장소: `treasonking/securityaiagent`, 작업 브랜치 `codex/scope-policy`.
- 시작 HTTP/문서 기준 `7ef40e1`; UI 브랜치 최신 확인값 `e54d776`. 두 이력을 merge `ce2343b`로 보존했다. main은 변경/병합하지 않았다.
- 구현·테스트 커밋: **`f36b6d5`**. 실제 명령은 `ce2343b` 위 개발 working tree에서 실행했고, 검증한 구현과 테스트를 이 커밋으로 고정했다. 이후 증거/결과 문서 커밋은 별도다.
- Windows PowerShell, Python **3.12.14**, Node **22.18.0**, npm **10.9.3**. pytest temp/cache만 gitignored `verification_tmp`로 지정했다.
- 실제 네 조합은 새 임시 loopback TCP target와 worker를 사용했다. 배포 origin `http://10.78.0.30:8080`, VM 네트워크/MAC/방화벽/RAM/CPU는 변경하지 않았다. 기존 사용자 서비스를 중단하지 않았다.

## 구현 결과

`config/targets.json` schema 2.0에 단일 origin과 `lab-access-control` revision 1 프로필을 결합했다. 엄격한 파싱·정규화는 `worker/registry.py`, `worker/scope.py`, 전역 한도는 `worker/limits.py`가 담당한다. `worker/service.py`는 세션 시작 전과 실제 HTTP 전송 직전에 run/target/account/operation/method/path/session을 검사한다. 허용되지 않은 요청은 전송하지 않는다.

실효 한도는 전역·프로필·시나리오 중 최솟값이다. HTTP 시나리오는 최대 HTTP 9회·도구 10회다. 전역 속도 0이어도 프로필 양수 속도가 유지된다. worker 시작 시 설정을 고정하며 파일 변경은 worker 재시작 후 적용된다. 실패 run은 재사용하지 않고 세션을 제거하며 TTL 뒤 회수한다.

worker가 반환한 정책 ID/revision/SHA-256/실효 한도만 finish·report·읽기 전용 UI에 표시한다. controller는 누락/변경을 거절하며 미완료는 `INCONCLUSIVE`다. report 1.0/1.1을 계속 읽고 구형 보고서의 해시는 추정하지 않는다. 입력칸 하단 유지/내부 스크롤/자동 높이 UI 변경을 보존했다. 해시는 동일성 추적용이지 서명이나 권한 증명이 아니다.

수정 영역: `worker/*`, `config/targets.json`, `common/schemas.py`, `controller/{engine,reporting}.py`, `frontend/src/{App.tsx,api.ts}`, 테스트와 loopback harness, README/AGENTS 및 운영·증거 문서. target/verifier의 판정 계약은 변경하지 않았다.

## 실제 실행한 검사

| 검사 | 최종 결과 |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest --tb=short` | **253 passed**, 7 dependency warnings, 147.11초 |
| frontend의 `npm test` | **14 passed**, 실패 0 |
| frontend의 `npm run build` | TypeScript/Vite build 성공 |
| `.\.venv\Scripts\python.exe -m worker.cli check-policy` | exit 0, 두 시나리오/실효 한도 출력, HTTP 요청 없음 |
| `.\.venv\Scripts\python.exe -c "from pathlib import Path; from scripts.run_http_verification import run_matrix; run_matrix(Path('reports/scope_policy'))"` | 실제 TCP 네 조합 성공, 아래 파일 보존 |
| `git diff --check`, `git diff --cached --check` | 성공; Git CRLF→LF 안내는 공백 오류가 아님 |
| 새 공개 산출물 검사 | 실제 실습 비밀번호, 세션 cookie 값, Bearer 값, target 응답 원문 없음 |

Python 실행 전 `PYTHONUTF8=1`, `PYTEST_DEBUG_TEMPROOT=<workspace>/verification_tmp`, `PYTEST_ADDOPTS=-o cache_dir=verification_tmp/pytest-cache`를 설정했다. 전체 테스트에는 기존 로그 판정·offline import·digest·취소·HTTP privacy 회귀가 포함된다. 7 경고는 Pydantic lifespan forward reference 1회와 SDK의 deprecated streamable transport helper 6회이며 실패가 아니다.

## 새 정책으로 직접 실행한 네 조합

원본 정제 matrix: [`matrix-a96fc4e51fbf.json`](scope_policy/matrix-a96fc4e51fbf.json). 각 run 폴더에 `report.json`, `report.md`, `evidence.json`을 보존했다. 모두 `COMPLETED`, provider `mock`, basis `http_observation`, 증거 **7개**, HTTP **9회**, 도구 **10회**, 거절 코드 배열 **`[]`**다.

| 모드 / 연결 | run ID와 보고서 | 판정 | 정책 SHA-256 |
|---|---|---|---|
| vulnerable / function | [`http-f0c757f54732429792a056884ca73362`](scope_policy/http-f0c757f54732429792a056884ca73362/report.json) | VULNERABLE | `3cb79db70b1a3ff33c2e4a24b22ecaf3fb11d767334238ca6b470182c69f27fb` |
| vulnerable / MCP | [`http-805902fcb8c846c6b848d5420298c969`](scope_policy/http-805902fcb8c846c6b848d5420298c969/report.json) | VULNERABLE | `3cb79db70b1a3ff33c2e4a24b22ecaf3fb11d767334238ca6b470182c69f27fb` |
| fixed / function | [`http-584a334bedad497f9c57adcb843d014e`](scope_policy/http-584a334bedad497f9c57adcb843d014e/report.json) | BLOCKED_BY_ACCESS_CONTROL | `2f52e1e4ac3e7e8637fa1692ab938cf4de62978bd1b2ce53884964912239a587` |
| fixed / MCP | [`http-5bb12f2158904d8ab564266917026495`](scope_policy/http-5bb12f2158904d8ab564266917026495/report.json) | BLOCKED_BY_ACCESS_CONTROL | `2f52e1e4ac3e7e8637fa1692ab938cf4de62978bd1b2ce53884964912239a587` |

모든 행의 profile ID는 `lab-access-control`, revision은 `1`이다. 실효값은 max_requests 9, max_tool_calls 10, timeout_seconds 5, run_timeout_seconds 180, max_response_bytes 65536, requests_per_second 2, max_concurrency 1, max_runs 100, state_ttl_seconds 600이다. 전체 값은 matrix/report에도 들어 있다.

각 모드에서 임시 target 포트가 달라 canonical origin이 바뀌므로 모드 사이 해시가 다르다. target mode 자체는 정책 해시나 HTTP verifier 입력에 포함하지 않는다. 배포 origin과 기본 전역 한도의 오프라인 검사 해시는 HTTP `3b68f75e546f09653322195a3f1a84051f7a8a7cd5d0e6bb5b8225c671dd4cb4`, 기존 로그 시나리오 `5291e06cb05b26973140bd8b51af594b0be584b1e7c9d205fc54c2114184dd8a`였다. 이는 파일 검사값이며 VM 실행 측정값이 아니다.

네 run 시작/종료는 2026-10-20 12:10:23–12:10:45 UTC 범위이며 행별 정확한 시각은 matrix에 있다. 각 판정 **후** evaluator가 target-local 요청 identity·계정·canary digest를 7/7 대조했다. 이 대조는 HTTP verifier 입력이 아니며 verifier의 log reader는 호출 시 실패하도록 설정했다. DB/로그 원문은 산출물에 없다.

## 거절·한도·호환 회귀

[`test_scope_policy.py`](../tests/test_scope_policy.py) **143개**와 기존 110개 회귀를 합쳐 위 전체 253개가 통과했다.

| 항목 | 확인 내용 |
|---|---|
| 설정 오류 | 아홉 한도 필드의 bool/0/음수/string/NaN/Infinity, 누락/unknown/중복/비활성/origin mismatch 명시 거절 |
| 사전 거절 | target/scenario/account/operation 위반은 상태/세션 생성 전 target 요청 0 |
| 양쪽 전송 | 실제 loopback REST function 및 SDK MCP에서 동일 worker 계정 거절, target 전송 0 |
| 전송 직전 검사 | origin/method/operation/account/session/cookie/payload 결합 및 semaphore 대기 후 세션 제거 재검사 |
| 경로 우회 | encoded path/authority/query/fragment/dot segment 차단; 기존 허용 로그인 이후 거절한 추가 전송 0 |
| 예산 우선순위 | global 2 vs profile 5 → 2회; global 8 vs profile 3 → 3회; HTTP scenario 상한 → 9회; N+1 전송 없음 |
| 기타 한도 | 프로필 응답 크기/요청시간/run시간 실제 중단, 속도 대기 취소, 동시성, max_runs/실패 상태 TTL |
| snapshot | 시작한 run 불변, 같은 worker의 신규 run도 기존 설정, 재시작 서비스만 revision 2 적용 |
| 완료 계약 | 두 시나리오 모두 finish 거절/정책 누락/해시 등 metadata 변경 시 INCONCLUSIVE |
| 호환/개인정보 | 실제 과거 report 읽기·정책 없음 유지, 기존 offline import/digest, events/report/UI 원문·비밀 차단 |
| UI | Node 상태 회귀와 소스/CSS 계약으로 입력 높이/하단 배치/내부 스크롤 확인; 실제 브라우저는 미실행 |

## 중간 실패 기록

- 기능 적용 전 HTTP+UI merge 기준 전체 **110 passed, 6 warnings**였다.
- 초기 집중 회귀는 **5 failed, 15 passed**: 새 구체적 scope reason code를 기존 `POLICY_REJECTED`로 기대하던 테스트 불일치였다. 요구한 실패 분류에 맞춰 기대값을 갱신했다.
- 첫 전체 회귀는 **2 failed, 241 passed, 7 warnings**: 기존 controller API 테스트의 5초 대기 한도를 프로필 2회/초 pacing이 넘었다. 테스트 전용 ASGI 설정에 명시적 양수 속도를 지정하고 파생 테스트 서비스도 그 registry를 전달하도록 수정했다. 배포 프로필 2회/초와 실제 네 조합의 제한은 완화하지 않았다.
- 초기 UI 결과 **13 passed, 1 failed**는 새 소스 검사 regex가 JSX arrow의 `>`에서 끊긴 문제였다. 검사식을 수정했고 최종 14개 통과했다. 당시 빌드도 성공했다.
- 수정 후 정책/API 집중 검사 149개가 통과했고, 위 최종 전체 253개가 통과했다. 과거 HTTP SQLite cleanup 실패, VM worker 422, bundle 전달, `TARGET_MODE` 명시적 로드 기록은 [기존 HTTP 결과](http_verification_results.md)에 그대로 보존했다.

## 2026-10-20 로컬 검증 당시의 미검증과 다음 단계

이번 결과는 Windows 로컬 mock 실행이다. **새 정책의 실제 VM/Ubuntu 동작, 실제 브라우저 화면·긴 대화 E2E, 외부 사이트 적용, 분산 worker 한도, OpenAI 추가 실호출**은 검증하지 않았다. Nmap/Playwright도 실행하지 않았다.

사용자 제공 기존 HTTP OpenAI 네 run은 controller 출력으로 보고된 성공이며, VM 원본 파일 직접 검사로 표현하지 않는다. 합계 4회·입력 952·출력 239·전체 1,191토큰과 개별 입력 238/출력 69·58·64·48은 [HTTP 결과](http_verification_results.md)와 [evidence index](evidence_index.md)에 보존·보완했다. 과거 run에 정책 해시·시각·VM 코드 버전을 추정해 넣지 않았다.

다음 작업은 [운영 가이드](../docs/scope_policy_runbook.md)의 **사용자가 다음에 실행할 VM 절차**다. `codex/scope-policy` bundle을 갱신해 worker 정책 검사/재시작, controller frontend 빌드/재시작, 모드별 target 환경의 명시적 로드를 수행하고 **허용·거절·한도** 세 가지를 확인한다. 이 문서의 로컬 실행 명령과 VM 권장 명령을 혼동하지 않는다. 실제 외부 버그 바운티 실행은 이 작업에 포함하지 않는다.

## 사용자 제공 VM scope 정책 6건 — 2026-10-22 기록

근거는 사용자가 제공한 `SecurityAI_Scope_VM_Results_Codex_20261022.md`의 정제 요약과 화면 확인 기록이다. 사용자는 controller VM의 `reports/runs/<run_id>/report.json` 및 `evidence.json`을 읽은 출력과 function/MCP 각 세 건의 화면·요약을 확인했다고 전달했다. **문서를 편집한 Codex가 VM 원본 JSON·화면·target DB를 직접 확보·검사한 결과가 아니다.** 원본 파일이나 화면을 확보한 것처럼 새 증거 파일·링크를 생성하지 않았다. 날짜는 기록일이며 개별 실행 시각은 미확인이다.

공통 조건은 `access-control-http`, `mock`, 등록 대상 `lab-web`, origin `http://10.78.0.30:8080`, `http_observation`, profile `lab-access-control`이다. provider는 function 화면, MCP 화면·출력에서 확인되었다는 사용자 기록이며 basis는 화면 확인 기록이다. UI의 `mode=unknown`은 HTTP verifier에 target mode 정답을 입력하지 않는 정상 표시다. 허용 run이 VULNERABLE로 관측되었지만 이번 여섯 실행의 별도 health 캡처는 제공되지 않아 target mode를 독립 확인한 것으로 기록하지 않는다.

| 연결 | 시험 | run ID | revision | 판정 | HTTP 보고 계수 | 도구 | 증거 |
|---|---|---|---:|---|---:|---:|---:|
| function | 허용 | `run_713d4db103fc460badb3a0a6af4591b6` | 1 | VULNERABLE | 9 | 10 | 7 |
| function | 계정 거절 | `run_39dfc5d3ecdb48d1bd7004904a8ac9a2` | 2 | INCONCLUSIVE | 1 | 1 | 0 |
| function | 한도 차단 | `run_99a5ea3be54e43f8ab17ca7b07178bce` | 3 | INCONCLUSIVE | 2 | 3 | 0 |
| MCP | 허용 | `run_d184b2c2c4954dd3b65c030aa5787afd` | 1 | VULNERABLE | 9 | 10 | 7 |
| MCP | 계정 거절 | `run_ed3e60f80bb345e8b36d0b21b7695bb9` | 2 | INCONCLUSIVE | 1 | 1 | 0 |
| MCP | 한도 차단 | `run_e6edada2a8d740e9b03ea8ca5b97d110` | 3 | INCONCLUSIVE | 2 | 3 | 0 |

두 transport의 revision별 `snapshot_sha256`은 사용자 제공값 기준으로 같다. 해시는 동일성 추적값이며 서명이나 권한 증명이 아니다.

| revision | snapshot_sha256 | max_requests |
|---|---|---:|
| 1 | `3b68f75e546f09653322195a3f1a84051f7a8a7cd5d0e6bb5b8225c671dd4cb4` | 9 |
| 2 | `dc699a1df2edbc2f44a4e7c8dcf37bb5457f351129bdeaf44e76a9a23bce3c57` | 9 |
| 3 | `2a7b6d4fc8666b6f233ee3aa25dcf58170d9dcf13bd7addf651934847ad7368d` | 2 |

나머지 실효 한도: `max_tool_calls=10`, `timeout_seconds=5`, `run_timeout_seconds=180`, `max_response_bytes=65536`, `requests_per_second=2`, `max_concurrency=1`, `max_runs=100`, `state_ttl_seconds=600`.

- r1은 user-a/user-b를 허용했다. 경고는 `Limited to these synthetic accounts, resource, and observation time; not a site-wide safety claim.` 하나다.
- r2는 원본 정책 복사본 `verification_tmp/scope-deny-user-b.json`의 HTTP 계정만 `[user-a]`로 축소했다. A 로그인 뒤 `start_session(user-b)`에서 `SCOPE_ACCOUNT_DENIED` / `account is outside the scope profile`로 중단됐다. HTTP/도구 보고 계수는 1/1, 증거는 0이다.
- r3는 원본 정책의 별도 복사본 `verification_tmp/scope-limit-two.json`에서 `max_requests=2`로 축소하고 두 계정을 허용했다. 로그인 두 번 뒤 `list_own_documents(user-a)`에서 `SCOPE_LIMIT_EXCEEDED` / `HTTP request limit exceeded`로 중단됐다. 도구 3회는 차단된 도구 진입을 포함하며 HTTP 보고 계수는 2다.
- 거절 시험의 `HTTP scenario evidence is missing, duplicated, or out of sequence`는 이 실행에서는 조기 중단에 따른 증거 부족 안내다. 실제 증거 중복이나 순서 오류가 발생했다는 뜻으로 해석하지 않는다. 네 거절/한도 run의 INCONCLUSIVE는 취약/차단 판정을 확정하지 않은 기대 동작이다.
- **HTTP 계수는 worker가 보고서에 기록한 값**이다. 거절 요청의 전송 0이나 N+1 미전송을 별도 패킷 캡처·target-local 로그로 독립 입증한 결과는 아니다.

### 사용자 보고 운영 이력과 복원 상태

인터넷이 격리된 worker는 Windows에서 만든 git bundle을 공유 폴더로 전달받아 scope 브랜치로 갱신했다. 초기 구버전의 `No module named worker.cli` 실패를 보존한다. 갱신 후 `check-policy`가 성공했으며 새 전역 Python/venv 생성 또는 DNS 변경으로 해결한 것이 아니다.

검사와 기동에 같은 `.env.worker`를 로드하고 프로세스별 `TARGET_REGISTRY_PATH`를 명시했다. 정책 변경마다 기존 worker를 Ctrl+C로 정상 종료 후 재시작했다. 실행 중 파일 변경의 자동 반영으로 설명하지 않는다. 실제 사용했다고 전달된 명령과 복원 명령은 [운영 가이드의 2026-10-22 보완](../docs/scope_policy_runbook.md#2026-10-22-사용자-보고-명령과-복원-주의)에 있다. **원본 정책 복원 완료 출력은 아직 없으므로 복원 완료로 단정하지 않는다.**

### 갱신된 확인 범위와 남은 작업

이번 추가로 VM mock function/MCP 각각의 허용·계정 거절·한도 차단은 **사용자 제공 출력·화면 확인 기록 수준**에서 예상 동작을 확인했다. 앞선 2026-10-20의 VM 미검증 표시는 당시 로컬 검사 범위다. 새 증거는 해당 여섯 run 범위만 보완하며, Codex의 VM 직접 재현·독립 검사 완료로 승격하지 않는다.

새 scope 버전의 **fixed 정상 실행 두 조합**은 이번 여섯 건에 없다. 실행 시각, VM별 commit SHA, Python/Node 버전, 독립 target 로그 대조, 정책 복원 확인은 미확인이다. 실제 브라우저 E2E, 외부 사이트, wildcard/DNS·일반 HTML 어댑터, Nmap/Playwright, 부하·장시간 안정성 검증도 포함하지 않는다. 합성 계정·리소스·시점의 결과를 사이트 전체 안전성이나 모델 탐지 정확도로 일반화하지 않는다.

새 scope 정책에서 OpenAI/GPT-6 Luna를 실제 호출한 증거가 아니며 기존 GPT-5.4-mini 네 run과 구분한다. 이번 변경은 문서만 수정했으며 코드·VM 설정 변경, 추가 OpenAI 호출, 테스트 재실행은 하지 않았다. 기존 **253개 Python/14개 UI** 결과는 2026-10-20 Windows 로컬 기록 그대로다. 다음 권장 작업은 원본 정책 복원 확인, VM별 실행 버전 기록, 새 scope의 fixed 정상 function/MCP 두 조합 확인이다.
