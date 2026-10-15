# Evidence index

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
