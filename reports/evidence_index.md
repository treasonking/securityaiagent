# Evidence index

## Codex 직접 실행 — API 어댑터 로컬 검증, 2026-10-27

[API 어댑터 검증 보고서](api_adapter_verification.md)와 [16건 원본 행렬](api_adapters/matrix-f36d4e7ff64b.json)에 documents/records × vulnerable/fixed × function/MCP의 정상 8건과 두 API의 계정·한도 거절 8건을 추가했다. provider는 모두 mock이며 HTTP 관찰만 사용했다. 정상 8건은 각 증거 7개·실제 HTTP 9회·도구 10회, 거절은 INCONCLUSIVE다. 모든 행에 정제된 report/evidence 파일이 연결돼 있다. 이는 Codex의 로컬 TCP 검증이며 사용자 VM 출력이나 VM 원본 직접 검증이 아니다. 이전 VM/OpenAI 결과와 실패 이력은 아래 기록을 유지한다.

## 기존 증거의 출처

이 인덱스는 2026-10-10·14 Codex가 직접 실행한 로컬 Windows 검증과 2026-10-14~15 첨부 가이드에 기록된 사용자 VM 결과를 분리한다. 첨부 가이드는 VM report 필드·target-local verifier JSON·DB 조회·UI 캡처를 근거로 작성됐다고 설명하지만, 그 원본 캡처와 파일은 이번 작업에 직접 첨부되지 않았다. VM run 파일과 DB도 이 Windows 작업 사본에 없었으므로, VM 행은 파일 직접 검사 결과가 아니다.

## Codex-verified local evidence — 2026-10-10

| Claim | Command / observation | Evidence path | Status | Limitation |
|---|---|---|---|---|
| vulnerable/fixed HTTP core and strict evidence paths work | isolated Python 3.12 `pytest` → 62 passed; local runs `local-vulnerable-4343327e3ec0` and `local-fixed-712a8c2cbf05`; evaluator 5/5 each | `tests/test_core_flow.py`, `tests/test_verifier_hardening.py`, `reports/current_verification.md` | Verified locally | mock + DirectToolClient + in-process ASGI; not VM function/MCP evidence |
| registered MCP VM Host is accepted without disabling DNS rebinding protection | Host boundary regression | `tests/test_mcp_integration.py` | Verified by header simulation | actual VM route/socket not tested |
| internal MCP ignores proxy environment | invalid SOCKS proxy env with successful loopback MCP run | `controller/tool_clients.py`, `tests/test_mcp_integration.py` | Verified locally | loopback only |
| cancellation stops rate/semaphore waits, externally cancelled acquire operations, and active HTTP | focused async regressions plus post-cancel slot reuse | `tests/test_worker_limits.py` | Verified locally | deterministic synthetic transports; remote disconnect not reproduced |
| controller deadline and queued cancellation are terminal-safe | provider timeout / queued API regressions | `tests/test_controller_api.py` | Verified locally | single process only |
| response byte limits preserve valid compression and cap decoded expansion | gzip/deflate JSON success; compressed gzip below 128B rejected after decoded expansion; raw stream rejects on third 64B chunk | `tests/test_worker_limits.py`, `worker/service.py` | Verified locally | synthetic transports, not an external compression server |
| HTTP request cap permits exactly N sends | N=1 and N=11 regressions, then N+1 rejection | `tests/test_worker_limits.py`, `worker/service.py` | Verified locally | per-run synthetic transport only |
| forged account/path/run/log evidence is rejected | mutation and offline DB regressions | `tests/test_verifier_hardening.py` | Verified locally | published fixture only |
| controller requires local access authentication and restart-stable logout | same-secret/same-DB signer restart rejects revoked token and preserves active token | `tests/test_controller_api.py`, `tests/test_controller_auth.py`, `controller/repository.py` | Verified locally | single-user SQLite registry; no external identity provider or distributed session store |
| offline final result updates report guidance consistently without exposing target DB | authenticated import changes INCONCLUSIVE to VULNERABLE, removes stale correlation warning, regenerates recommendations | `tests/test_controller_api.py`, `verifier/cli.py` | Verified locally | bearer token holder is a trusted operator; distribution is operator-managed |
| UI has provider selection, empty-candidate/verifier separation, run restoration, atomic terminal snapshots, async conversation/run guards, SSE cleanup/poll fallback | `npm test` → 11 passed, including delayed details, stale conversation responses, and empty-candidate contract; `npm run build` success | `frontend/tests/run-refresh.test.mjs`, `frontend/tests/security-contract.test.mjs`, `frontend/src/run-refresh.js`, `frontend/src/App.tsx` | Verified in Node state harness and statically | no real browser E2E or screenshot |
| OpenAI candidate contract preserves canonical/empty outcomes and rejects noncanonical/API failure | network-free stub Runner; provider and engine regressions | `tests/test_provider.py`, `tests/test_core_flow.py`, `controller/providers.py` | Verified locally without API | does not validate account access, live model behavior, latency, or billing |
| VM isolation and resource allocation | not run | `docs/network_setup.md` | Not verified | requires user-owned VMs |
| Nmap / Playwright | intentionally not run | `docs/phase2_nmap_playwright.md` | Not implemented (phase 2) | no tool/dependency in v1 |

The 2026-10-14 Python run emitted four MCP/Agents SDK dependency warnings—one Pydantic forward-reference warning and three deprecated transport-helper warnings—plus one local `PytestCacheWarning` because the existing `.pytest_cache` directory was not writable. None failed the tests; the dependency warnings must be reassessed when dependencies change.

## User-reported VM result index — 2026-10-14

The attached guide records one `mock` execution for each vulnerable/fixed × function/MCP combination. It reports that all four had five sanitized evidence items, 5/5 target-local correlation, an empty `warnings` array, and manual UI import. Codex confirmed that none of the listed VM run directories or databases exists in this Windows checkout. The expected paths below are VM-side paths recorded in the guide, not repository-tracked evidence.

| Mode / transport | Run ID and reported result | Reported sanitized paths | Evidence digest | Acquisition status |
|---|---|---|---|---|
| vulnerable / function | `run_9a446c4d55464f75b834becc747144c0`; `VULNERABLE`; 5/5 | controller and target: `reports/runs/run_9a446c4d55464f75b834becc747144c0/evidence.json`; target: `offline_verification.json` in the same run directory | `a53d821688b2b5ff98844cf1bc516b14909448edd7ee9c0da819aa52f1b4e940` | metadata recorded in attached guide; underlying files not present or inspected locally |
| vulnerable / MCP | `run_00d1dddd988049a09e64783d8b4d886a`; `VULNERABLE`; 5/5 | controller and target: `reports/runs/run_00d1dddd988049a09e64783d8b4d886a/evidence.json`; target: `offline_verification.json` in the same run directory | `7680654e6f2badb2688fd872359a31c546516aa3f5d9029a080b051ed95d5948` | metadata recorded in attached guide; underlying files not present or inspected locally |
| fixed / function | `run_e859f540f64245e3acc16a2ccb1d9985`; `BLOCKED_BY_ACCESS_CONTROL`; 5/5 | controller and target: `reports/runs/run_e859f540f64245e3acc16a2ccb1d9985/evidence.json`; target: `offline_verification.json` in the same run directory | `4762e24dfac30c0ebbd0ff7f02e1afcb9e69df349dc2d4e41f29ba3ac6726dd9` | metadata recorded in attached guide; underlying files not present or inspected locally |
| fixed / MCP | `run_367d971796d8484db0441d251d1d293c`; `BLOCKED_BY_ACCESS_CONTROL`; 5/5 | controller and target: `reports/runs/run_367d971796d8484db0441d251d1d293c/evidence.json`; target: `offline_verification.json` in the same run directory | `8a0688d49c30850a199d0a994d4840decc07c6370f01ebc9365b3614494b7439` | metadata recorded in attached guide; underlying files not present or inspected locally; restart persistence reported |

The digest checks identity consistency between sanitized evidence and an imported result; a digest alone does not prove provenance or provide independent audit attestation. The exact VM execution commit is not confirmed. Commit `6e9f4f5` identifies the reviewed Windows `main` before this documentation update, not necessarily the VM runtime commit.

### Database boundary and acquisition state

- The user reported the initial vulnerable target DB as target-local `data/vm-target.sqlite3`. A preserved copy was requested at target-local `data/vm-target-vulnerable.sqlite3`, but Codex did not verify that this copy exists.
- The fixed target DB was reported as target-local `data/vm-target-fixed.sqlite3`.
- The live vulnerable target DB was reported as target-local `data/vm-target-live-vulnerable.sqlite3`.
- Controller state remains separate at controller-local `data/securitylab.sqlite3`.
- None of these VM DB files was found in this checkout. Raw target DBs and logs must remain on the target/evaluator boundary and must not become controller, model, UI, or public-report inputs.
- Only sanitized evidence metadata and `offline_verification.json` may cross that boundary for authenticated import. Shared clipboard was used for the reported runs, so clipboard isolation is not evidence here.

## User-reported first live OpenAI result — 2026-10-14

| Run ID | Reported provider result | Reported verifier result | Evidence digest | Acquisition status |
|---|---|---|---|---|
| `run_8d464c88140f447d9fd7a794136545d4` | fixed / OpenAI / function; `gpt-5.4-mini`; completed; 1 call; 119 input, 73 output, 192 total tokens; candidates `[]` | `BLOCKED_BY_ACCESS_CONTROL`; evidence 5; correlation 5/5; warnings `[]`; manual import and UI `offline-correlated` | `bbb9b86ba46c262efdb4736039670b1d9df0e8755df41ec16bedabf2d0a2027c` | metadata recorded in attached guide; run files and captures not present or inspected locally |

This pre-fix record demonstrates neither why the stored candidate list was empty nor model detection quality. The application did not retain the pre-filter model output, so an intentional empty list and a filtered noncanonical name cannot be distinguished retrospectively. The reported API usage is not a cost hard cap and does not reveal provider retries or final billing. The post-fix representative matrix is recorded separately below; this historical run is not merged into it.

## User-reported post-fix live OpenAI matrix — 2026-10-14 to 2026-10-15

The attached guide reports that each representative row below completed with provider `openai`, model `gpt-5.4-mini`, one SDK-reported call, one canonical `cross_account_document_access` candidate from `openai_provider`, five sanitized evidence items, target-local correlation 5/5, offline warnings `[]`, and a final UI state of `offline-correlated`. The listed controller/target paths are expected VM-side paths. None exists in this Windows checkout.

| Mode / transport | Run ID, usage, verdict | Reported sanitized paths | Evidence digest | Acquisition status |
|---|---|---|---|---|
| fixed / function | `run_0c128a3c7c0743798c27d2a2830468e5`; 237 input / 54 output / 291 total; `BLOCKED_BY_ACCESS_CONTROL` | controller and target: `reports/runs/run_0c128a3c7c0743798c27d2a2830468e5/evidence.json`; target: `offline_verification.json` in the same run directory | `12112b54cbfa5dd2748fabf13eb6b0306b218dddf1cfc48000fb90210a8ef341` | metadata recorded in attached guide; files not present or inspected locally |
| fixed / MCP | `run_ea64269013f44d5793dadccda43dcc31`; 237 input / 64 output / 301 total; `BLOCKED_BY_ACCESS_CONTROL` | controller and target: `reports/runs/run_ea64269013f44d5793dadccda43dcc31/evidence.json`; target: `offline_verification.json` in the same run directory | `634167d7436e7686cc44234212bb2347e250325c0a2ca95a44b2b485ca63332b` | metadata recorded in attached guide; files not present or inspected locally |
| vulnerable / function | `run_b58e5aece9d7496396c45205f3dc6046`; 237 input / 62 output / 299 total; `VULNERABLE` | controller and target: `reports/runs/run_b58e5aece9d7496396c45205f3dc6046/evidence.json`; target: `offline_verification.json` in the same run directory | `1818aef9cb72b7824d0805dfa26b5497537c4978ae80ffd74b8789b76dddb980` | metadata recorded in attached guide; files not present or inspected locally |
| vulnerable / MCP | `run_4aa1b9b6e7fe4e0487af9ee1eeeb1ea0`; 237 input / 61 output / 298 total; `VULNERABLE` | controller and target: `reports/runs/run_4aa1b9b6e7fe4e0487af9ee1eeeb1ea0/evidence.json`; target: `offline_verification.json` in the same run directory | `247488121399b86739b9c8a90ab74abc9af8e2111b1a3f7bf11eb39feb1b88fb` | metadata recorded in attached guide; files not present or inspected locally |

Representative-success totals are four SDK-reported calls, 948 input tokens, 241 output tokens, and 1,189 total tokens. They exclude the pre-fix run and retry history and do not represent billing or provider-internal retry counts. For the final successful MCP run, the guide records 22 total target observations and 11 observations for that run; only five sanitized items are decision evidence.

The reviewed contract commit is `f2407f816c8fe73ce88bd96c1a78293c19d59c0e`, but no `git rev-parse HEAD` value was supplied for the actual controller, worker, or target execution. Code parity across the three VMs is therefore not independently established.

### Unsuccessful and unverified retry evidence

| Run ID | Reported evidence | Status |
|---|---|---|
| `run_20b9caa5720b4b1dbcb6d9a6a034a009` | vulnerable/OpenAI/MCP; UI candidate and five evidence items; offline `INCONCLUSIVE`, correlation 0/5; digest `0e1380c4d87b8029c56bceddd1f114c772dd47e2dcfcc57b3218305721323855`; no matching target observations in DBs checked by the user | failed correlation; not a successful final result |
| `run_4139a4ebe3ed4208ac624e80f447e518` | vulnerable/OpenAI/MCP retry; UI candidate and five evidence items; offline result and usage not retained | final verdict unverified; not a successful final result |

After a target shutdown/restart around `run_20b9...`, the guide records a query showing zero total observations in `data/vm-target-live-vulnerable.sqlite3`. The cause was not established; restart is not documented as normal log deletion. The final `run_4aa1...` is a separate successful execution and must not be used to convert either retry into success.

### Operational-log boundary

The guide reports reduced target stdout (`--no-access-log`, warning log level, redirection to `logs/target-server.log`) before the last successful MCP run. This is a screen-output mitigation, not a root-cause fix. It does not disable SQLite observations or verifier evidence. `logs/target-server.log` was not present in this checkout and remains a target-local diagnostic artifact whose contents, size, and retention were not reviewed.

## Still not verified

- Independent reproduction/file inspection of the live matrix; model accuracy, cost, latency, provider retries, or billing
- Automated browser E2E, Nmap, and Playwright
- Full firewall/routing/IPv6/egress isolation, every negative path, or service authentication inferred from health endpoints
- Repeatability, load, stability, or detection-rate metrics from more than one representative run per combination
- Root cause of the target freeze, missing observations, or worker slowdown


## Codex-verified local HTTP-only evidence — 2026-10-15

- 구현 커밋 `b97baf9`, 기준 main `17d72b8`. [전체 실행 결과/실패 이력](http_verification_results.md), [재현 가이드](../docs/http_verification_runbook.md).
- 최종 Windows loopback 실제 TCP target + worker, mock vulnerable/fixed × function/MCP 네 조합: [matrix-5cba34249eb5.json](http_verification/matrix-5cba34249eb5.json). 각 run 증거 7개, HTTP 9회, 도구 10회, 기준 `http_observation`; 사후 독립 로그 대조 7/7씩. target DB/log/mode는 HTTP verifier 입력이 아니다.
- 최종 회귀: Python 110 passed (6 dependency warnings), UI Node/소스 검사 12 passed, TypeScript/Vite build 성공. 기존 main 별도 기준 검증 62 passed.
- 초기 Python 경로/ACL 오류 및 첫 matrix의 SQLite cleanup 실패도 결과 문서에 보존했다. 초기 네 run은 최종 판정 계약 이전의 개발 중 기록이며 최종 증거로 재해석하지 않는다.
- VM/Ubuntu/OpenAI 실호출/실제 브라우저 E2E는 이번 실행에서 검증하지 않았다. Nmap/Playwright도 실행하지 않았다. 이전 VM 기록과 로컬 증거는 위에 그대로 유지한다.

## User-reported VM HTTP-only matrix — 2026-10-16 기록

시나리오 `access-control-http`의 실제 VM 실행 결과를 사용자 보고로 추가한다. 공통 보고값은 `provider=mock`, `verification_basis=http_observation`, 각 실행 증거 7개다. 사용자는 첨부 화면에서 판정을 확인했다고 보고했으나, 이번 문서 업데이트에서 화면 원본을 직접 열람하거나 VM 원본 JSON을 대조하지 않았다. **사용자 보고 / 화면 판정 확인 보고 / 원본 JSON 미대조**이며, 위의 Codex 직접 실행 로컬 결과와 구분한다. 날짜는 보고 기록일이고 개별 실행 시각은 미제공이다.

| VM 모드 / transport | run ID | 판정 (사용자 보고) | 증거 수 (사용자 보고) | 확인 수준 |
|---|---|---|---|---|
| vulnerable / function | `run_bc9c414b6860453886d4174dc405459b` | `VULNERABLE` | 7 | 화면 확인 보고, 원본 JSON 미대조 |
| vulnerable / mcp | `run_74e63dc639ec497782a9f84c8444f7a2` | `VULNERABLE` | 7 | 화면 확인 보고, 원본 JSON 미대조 |
| fixed / function | `run_54001251a18a463ea9a617162bfec8f5` | `BLOCKED_BY_ACCESS_CONTROL` | 7 | 화면 확인 보고, 원본 JSON 미대조 |
| fixed / mcp | `run_9d4d0eea1ed1468eace1784a0915ac68` | `BLOCKED_BY_ACCESS_CONTROL` | 7 | 화면 확인 보고, 원본 JSON 미대조 |

- 운영 이력도 사용자 보고로 보존한다: **이전 버전 worker로 인한 422 실패**, **격리망에 `git bundle`로 코드 전달**, **`TARGET_MODE`를 target 실행 환경에 명시적으로 로드한 뒤 재시작**. 실패 run ID/원본 오류, bundle 해시·명령, VM별 적용 커밋과 실제 재시작 명령은 미제공이다. 성공한 네 run으로 이전 실패를 덮어쓰지 않는다.
- [VM 결과·운영 절차·확인 수준 상세](http_verification_results.md)의 사용자 보고 절을 참고한다. VM JSON·digest·실행 시간·호출 수·독립 로그 대조 결과는 아직 확인하지 않았으며 로컬 수치를 대신 넣지 않는다. 다음 작업은 VM 정제 원본 JSON 및 실행 버전 대조다.
- 이 mock 결과 보고 당시에는 새 HTTP 시나리오의 OpenAI 실호출 및 외부 사이트 적용이 미검증이었다. 후속 HTTP OpenAI 출력은 아래 별도 절에 추가한다. 위의 기존 로그 기반 `access-control` OpenAI 기록과 혼동하지 않는다. 실제 브라우저 E2E나 격리망 전체 보안 검증을 완료했다고 주장하지 않는다.
- 이번 변경은 두 문서에 한정하며 코드·기존 증거 파일은 변경하지 않았다. 테스트는 재실행하지 않았고 기존 로컬 성공/실패 기록은 보존했다.

## User-provided controller JSON output: HTTP OpenAI matrix — 2026-10-16 기록

**사용자가 controller에서 실행하여 이번 대화에 제공한 JSON 출력의 전달값**을 근거로 기록한다. Codex의 VM 원본 파일 직접 검사·독립 재실행 결과가 아니다. 공통값은 `scenario_id=access-control-http`, `provider=openai`, 모델 `gpt-5.4-mini`, `COMPLETED`, 실행별 호출 1회·증거 7개, `verification_basis=http_observation`이다.

| VM 모드 / transport | run ID | verdict | 입력 / 출력 / 전체 토큰 | 저장 증거 재판정 (사용자 제공 출력) |
|---|---|---|---|---|
| fixed / function | `run_3dd2ccc895c249ed95e7551f5b5156fa` | `BLOCKED_BY_ACCESS_CONTROL` | 238 / 69 / 307 | `verdict_matches=true` |
| fixed / MCP | `run_85d5635cf09641fc88b5f920702bc4d4` | `BLOCKED_BY_ACCESS_CONTROL` | 238 / 58 / 296 | `verdict_matches=true` |
| vulnerable / function | `run_dcb89c46afdd4461a5f727d06bdd8815` | `VULNERABLE` | 238 / 64 / 302 | `verdict_matches=true` |
| vulnerable / MCP | `run_118cdedf22fa4a09871bc74b305266d5` | `VULNERABLE` | 238 / 48 / 286 | `verdict_matches=true` |

- 합계: **호출 4회 · 입력 952 · 출력 239 · 전체 1,191토큰**. 행별 전체 토큰 및 입력/출력 합계가 일치한다. 개별 입력/출력 분할은 2026-10-20 사용자가 적용 요청한 `SecurityAI_Scope_Profile_Codex_Task.md`의 전달값으로 보완했다. 이전 실행·실패·재시도나 실제 청구액의 합계로 해석하지 않는다.
- 확인 수준: **사용자 제공 controller 출력에서 완료·예상 판정·재판정 일치 확인**. `verdict_matches=true`는 사용자 제공 출력이며 Codex의 원본 증거 재판정이나 target 로그 독립 대조를 뜻하지 않는다. VM 원본 파일·실행 커밋·환경·시각의 직접 검사는 미실시다.
- [실행 결과와 한계 상세](http_verification_results.md)의 HTTP OpenAI 절을 참고한다. 기존 mock 결과와 실패 이력은 위에 보존하며, 기존 로그 기반 OpenAI 실험과도 분리한다.
- **외부 사이트 적용은 미검증**으로 유지한다. 모델 탐지 성능, 실제 브라우저 E2E, Nmap/Playwright 및 전체 격리망 보안 검증을 입증한 것으로 기록하지 않는다.
- 문서 두 파일만 갱신했다. 코드 변경·추가 OpenAI 호출·테스트 재실행은 하지 않았다.

## Codex-verified scope profile local evidence — 2026-10-20

- 위 2026-10-16 기록과 별개의 구현 작업이다. [정책 검증 보고서](scope_policy_verification.md), [정책 운영 가이드](../docs/scope_policy_runbook.md), [실제 네 조합 matrix](scope_policy/matrix-a96fc4e51fbf.json)를 추가했다.
- Windows loopback 실제 TCP target+worker, mock vulnerable/fixed × function/MCP 네 run의 정제 report/evidence가 `scope_policy/<run_id>/`에 있다. 각 run 증거 7개, HTTP 9회, 도구 10회, `http_observation`, 정책 `lab-access-control` revision 1, 거절 없음 `[]`. 각 row의 전체 SHA-256/실효 한도는 matrix에 보존했다.
- 사전 계정·시나리오·작업 거절은 target 전송 0, 허용 N회 뒤 N+1 거절, 세션·origin·경로 결합, 불변 snapshot/재시작 규칙, metadata 불일치·미완료 INCONCLUSIVE는 [`tests/test_scope_policy.py`](../tests/test_scope_policy.py)의 별도 로컬 회귀다.
- 기존 mock/VM/OpenAI/실패 이력을 유지했다. 사용자 제공 OpenAI 결과는 VM 원본 직접 검사 증거가 아니며, 원문에 없는 정책 해시·digest·실행 버전·시각은 추정하지 않는다. 합성 계정·리소스·시점 범위 경고도 유지한다.
- 새 정책 VM 적용, Ubuntu, 실제 브라우저 E2E, 외부 사이트는 미검증이다. OpenAI 추가 호출, VM 네트워크/방화벽/자원 변경은 하지 않았다.

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

## 사용자 제공 fixed VM UI 결과 — 2026-10-27 기록

사용자가 **fixed로 설정했다고 보고한 대상**에서 다음 두 실행을 확인했다. 근거는 사용자 제공 UI 출력이며, Codex가 VM 원본 report/evidence 파일 또는 target DB·health를 직접 확보·검사한 검증과 구분한다. 기록일은 실행 시각을 뜻하지 않는다.

| 연결 | run ID | provider | 정책 | 판정 | 증거 | verification_basis |
|---|---|---|---|---|---:|---|
| function | `run_d06a266cdf1d47e4ad93d211aedcb04e` | mock | lab-access-control r1 | BLOCKED_BY_ACCESS_CONTROL | 7 | http_observation |
| MCP | `run_57331e256fa1436894338528c7a1245d` | mock | lab-access-control r1 | BLOCKED_BY_ACCESS_CONTROL | 7 | http_observation |

이 두 건으로 이전 절에서 미확인이었던 **새 scope의 fixed 정상 function/MCP 두 조합**을 사용자 제공 UI 출력 수준에서 보완한다. UI 정책 한도는 허용 상한이며 **실제 HTTP 요청·도구 사용량은 미제공**이다. 9회/10회를 측정값으로 복사하지 않는다. 정책 해시, 실행 시각, VM별 commit SHA, 환경 버전, 원본 정책 복원 명령/출력, 독립 target 로그 대조도 새로 제공되지 않았으므로 추정하지 않는다. r1 표시만으로 이전 시험 후 정책 파일 복원 절차 전체가 검증됐다고 보지 않는다.

기존 6건·로컬 테스트·OpenAI·실패 이력은 보존한다. 결과는 합성 계정·리소스·시점에 한정하며 외부 사이트 안전성이나 모델 정확도 증거가 아니다. 추가 OpenAI 호출이나 VM 재실행 없이 문서에 기록했다. 후속 서비스별 API·인증 설정 분리는 이 VM 결과를 새로운 구현의 검증 증거로 재사용하지 않고 별도로 검증한다.

## 서비스별 설정 분리 로컬 검증 — 2026-10-27

[별도 구현·검증 기록](service_configuration_verification.md): 새 브랜치 `codex/service-auth-config`, Python 284 passed (신규 설정 검사 31개 포함), UI 14 passed, TypeScript/Vite build 및 diff 검사 성공. worker scope 해석 경로와 인증 계약을 유지한다. 새 launcher의 실제 VM 기동은 미검증이며 사용자 제공 fixed UI 결과와 구분한다.
