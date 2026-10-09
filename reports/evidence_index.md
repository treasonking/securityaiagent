# Evidence index

2026-10-09 로컬 Windows 개발 환경 기준이다. VM, live OpenAI, 실제 브라우저 evidence로 해석하지 않는다.

| Claim | Command / observation | Evidence path | Status | Limitation |
|---|---|---|---|---|
| vulnerable/fixed HTTP core and strict evidence paths work | `.\.venv\Scripts\python.exe -m pytest` → 53 passed; local core + evaluator | `tests/test_core_flow.py`, `tests/test_verifier_hardening.py` | Verified locally | target uses in-process ASGI in core run |
| registered MCP VM Host is accepted without disabling DNS rebinding protection | Host boundary regression | `tests/test_mcp_integration.py` | Verified by header simulation | actual VM route/socket not tested |
| internal MCP ignores proxy environment | invalid SOCKS proxy env with successful loopback MCP run | `controller/tool_clients.py`, `tests/test_mcp_integration.py` | Verified locally | loopback only |
| cancellation stops rate/semaphore waits, externally cancelled acquire operations, and active HTTP | focused async regressions plus post-cancel slot reuse | `tests/test_worker_limits.py` | Verified locally | deterministic synthetic transports; remote disconnect not reproduced |
| controller deadline and queued cancellation are terminal-safe | provider timeout / queued API regressions | `tests/test_controller_api.py` | Verified locally | single process only |
| response byte limits preserve valid compression and cap decoded expansion | gzip/deflate JSON success; compressed gzip below 128B rejected after decoded expansion; raw stream rejects on third 64B chunk | `tests/test_worker_limits.py`, `worker/service.py` | Verified locally | synthetic transports, not an external compression server |
| HTTP request cap permits exactly N sends | N=1 and N=11 regressions, then N+1 rejection | `tests/test_worker_limits.py`, `worker/service.py` | Verified locally | per-run synthetic transport only |
| forged account/path/run/log evidence is rejected | mutation and offline DB regressions | `tests/test_verifier_hardening.py` | Verified locally | published fixture only |
| controller requires local access authentication and restart-stable logout | same-secret/same-DB signer restart rejects revoked token and preserves active token | `tests/test_controller_api.py`, `tests/test_controller_auth.py`, `controller/repository.py` | Verified locally | single-user SQLite registry; no external identity provider or distributed session store |
| offline final result updates report guidance consistently without exposing target DB | authenticated import changes INCONCLUSIVE to VULNERABLE, removes stale correlation warning, regenerates recommendations | `tests/test_controller_api.py`, `verifier/cli.py` | Verified locally | bearer token holder is a trusted operator; distribution is operator-managed |
| UI has provider selection, run restoration, async conversation/run guards, SSE cleanup/poll fallback | `npm test` → 8 passed, `npm run build` success | `frontend/tests/security-contract.test.mjs`, `frontend/src/App.tsx` | Verified statically | no delayed-response browser E2E or screenshot |
| OpenAI provider runs with a real model | not run | `controller/providers.py` | Not verified | no API key/model authorization supplied |
| VM isolation and resource allocation | not run | `docs/network_setup.md` | Not verified | requires user-owned VMs |
| Nmap / Playwright | intentionally not run | `docs/phase2_nmap_playwright.md` | Not implemented (phase 2) | no tool/dependency in v1 |

Python warnings are four MCP/Agents SDK dependency warnings: one Pydantic forward-reference warning and three deprecated transport-helper warnings. They do not fail the current tests but must be reassessed when dependencies change.
