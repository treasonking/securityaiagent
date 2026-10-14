# Evidence index

이 인덱스는 2026-10-10 Codex가 직접 실행한 로컬 Windows 검증과 2026-10-14 첨부 가이드에 기록된 사용자 VM 결과를 분리한다. 첨부 가이드는 VM 터미널·오프라인 JSON·UI 관찰을 근거로 작성됐다고 설명하지만, 그 원본 캡처와 파일은 이번 작업에 직접 첨부되지 않았다. VM run 파일과 DB도 이 Windows 작업 사본에 없었으므로, VM 행은 파일 직접 검사 결과가 아니다.

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
- Controller state remains separate at controller-local `data/securitylab.sqlite3`.
- None of these VM DB files was found in this checkout. Raw target DBs and logs must remain on the target/evaluator boundary and must not become controller, model, UI, or public-report inputs.
- Only sanitized evidence metadata and `offline_verification.json` may cross that boundary for authenticated import. Shared clipboard was used for the reported runs, so clipboard isolation is not evidence here.

## User-reported first live OpenAI result — 2026-10-14

| Run ID | Reported provider result | Reported verifier result | Evidence digest | Acquisition status |
|---|---|---|---|---|
| `run_8d464c88140f447d9fd7a794136545d4` | fixed / OpenAI / function; `gpt-5.4-mini`; completed; 1 call; 119 input, 73 output, 192 total tokens; candidates `[]` | `BLOCKED_BY_ACCESS_CONTROL`; evidence 5; correlation 5/5; warnings `[]`; manual import and UI `offline-correlated` | `bbb9b86ba46c262efdb4736039670b1d9df0e8755df41ec16bedabf2d0a2027c` | metadata recorded in attached guide; run files and captures not present or inspected locally |

This pre-fix record demonstrates neither why the stored candidate list was empty nor model detection quality. The application did not retain the pre-filter model output, so an intentional empty list and a filtered noncanonical name cannot be distinguished retrospectively. The reported API usage is not a cost hard cap and does not reveal provider retries or final billing. A new fixed/OpenAI/function run against the hardened contract has not yet been supplied; live MCP and vulnerable-mode live runs remain separate future checks.

## Still not verified

- Post-change live OpenAI candidate behavior, model quality, cost, latency, provider retries, or billing
- Automated browser E2E, Nmap, and Playwright
- Full firewall/routing/IPv6/egress isolation, every negative path, or service authentication inferred from health endpoints
- Repeatability or detection-rate metrics from more than one run per VM combination
- Independent Codex reproduction and file-level inspection of the four VM runs
