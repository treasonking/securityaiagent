# SecurityLab v1 hardening verification — 2026-10-09

## Verified locally

| Area | Command / test | Result |
|---|---|---|
| Python core/API/MCP | `.\.venv\Scripts\python.exe -m pytest` | 45 passed, 4 dependency warnings |
| React security/state contract | `npm test` | 8 passed; source contract tests, not browser E2E |
| React production build | `npm run build` | success, 17 modules transformed |
| vulnerable fixture | `scripts\run_local_core.py --mode vulnerable` | `VULNERABLE`, 11 HTTP requests, 12 tool calls, 5 evidence items |
| fixed fixture | `scripts\run_local_core.py --mode fixed` | `BLOCKED_BY_ACCESS_CONTROL`, 11 HTTP requests, 12 tool calls, 5 evidence items |
| offline correlation | `python -m verifier.cli evaluate ...` | vulnerable/fixed 각각 5/5 correlated, 판정 재현 |
| MCP Host boundary | `test_mcp_transport_accepts_registered_vm_host_and_rejects_other_hosts` | 등록 `10.77.0.20:9000` 성공, 미등록 Host 421, 미등록 Origin 403, 무인증 401 |
| MCP environment proxy isolation | proxy 환경변수를 유효하지 않은 SOCKS URL로 설정한 MCP integration | loopback 도구 탐색·호출 성공; 내부 MCP client `trust_env=False` |
| cancellation/deadline | rate-limit, semaphore, active HTTP, queued run, provider deadline tests | 대기 취소 뒤 추가 request 0; active task 취소; controller `TIMED_OUT` 확인 |
| streaming response cap | 16×64B custom stream / 128B cap | 세 번째 chunk에서 거부; 나머지 13 chunks 미다운로드 |
| verifier identity hardening | wrong account/path/run, duplicate evidence, forged correlation flag | 모두 `INCONCLUSIVE` 또는 import 거부 |
| local authentication | unauthenticated/wrong token, random session, expiry, revoke/logout, CSRF, Host/client allowlist | expected rejection and authenticated access confirmed |
| offline result import | bearer-authenticated sanitized result + evidence digest | bad token/digest rejected; accepted result updates controller report/UI state |

The local run IDs were `local-vulnerable-a64953c3af71` and `local-fixed-d936d2d0443b`. Generated run directories, SQLite files, virtual environments, frontend dependencies, and build output are gitignored runtime artifacts.

The MCP Host result uses a TestClient request whose Host header is the documented VM address. It proves the application allowlist behavior, not connectivity to an actual VM. The loopback MCP integration starts a real Uvicorn socket and uses the Agents SDK `MCPServerStreamableHttp` client, while its synthetic target remains in-process ASGI.

## Not verified

- VirtualBox/VMware VM creation, actual `10.77.0.20:9000` connectivity, NIC roles, routing, forwarding, firewall rules/counters, and negative network paths
- real OpenAI API call, account model access, output quality, retries, token usage, cost, and latency
- real browser behavior for login, provider selection, refresh, conversation switching, SSE reconnect/polling, visual layout, or screenshots
- Nmap installation/execution and Playwright browser/egress enforcement
- TLS/mTLS, multiple controller processes/users, long-duration load, and memory behavior

## Interpretation limit

These results reproduce one synthetic access-control fixture and hardening boundaries around that workflow. They do not measure generalized vulnerability discovery, production-site security, or model performance. Mock provider calls remain zero model calls and are not a local LLM result. A `COMPLETED` workflow may still have an `INCONCLUSIVE` verdict; final claims require the verifier result and, for socket-separated target runs, authenticated offline correlation.
