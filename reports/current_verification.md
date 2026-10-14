# SecurityLab v1 scenario verification — updated 2026-10-14

## Verified locally

| Area | Command / test | Result |
|---|---|---|
| Python core/API/MCP | isolated Python 3.12 venv: `python -m pytest` | 53 passed; 4 dependency warnings + 1 local `.pytest_cache` ACL warning |
| React security/state regression | `npm test` | 10 passed; two delayed-response state tests plus source contracts, not browser E2E |
| React production build | `npm run build` | success, 18 modules transformed |
| vulnerable fixture | `scripts\run_local_core.py --mode vulnerable` | `VULNERABLE`, 11 HTTP requests, 12 tool calls, 5 evidence items |
| fixed fixture | `scripts\run_local_core.py --mode fixed` | `BLOCKED_BY_ACCESS_CONTROL`, 11 HTTP requests, 12 tool calls, 5 evidence items |
| offline correlation | `python -m verifier.cli evaluate ...` | vulnerable/fixed 각각 5/5 correlated, 판정 재현 |
| MCP Host boundary | `test_mcp_transport_accepts_registered_vm_host_and_rejects_other_hosts` | 등록 `10.77.0.20:9000` 성공, 미등록 Host 421, 미등록 Origin 403, 무인증 401 |
| MCP environment proxy isolation | proxy 환경변수를 유효하지 않은 SOCKS URL로 설정한 MCP integration | loopback 도구 탐색·호출 성공; 내부 MCP client `trust_env=False` |
| cancellation/deadline | rate-limit, semaphore, active HTTP, queued run, provider deadline tests | 대기 취소 뒤 추가 request 0; active task 취소; controller `TIMED_OUT` 확인 |
| external task cancellation | semaphore 선점 중 대기 task 직접 취소 후 다음 요청 실행 | abandoned acquire 회수, 다음 정상 작업이 유일 슬롯 획득 |
| streaming/compression cap | 16×64B stream / 128B cap, gzip·deflate JSON, 압축된 과대 gzip | 세 번째 chunk에서 거부; gzip/deflate 단일 해제 성공; 압축 크기 128B 미만이어도 해제 후 cap 거부 |
| exact HTTP request cap | `max_requests=1` 및 `11` | 정확히 N회 성공, N+1번째는 transport 진입 전 거부 |
| verifier identity hardening | wrong account/path/run, duplicate evidence, forged correlation flag | 모두 `INCONCLUSIVE` 또는 import 거부 |
| local authentication | unauthenticated/wrong token, random session, expiry, revoke/logout, same-secret restart, CSRF, Host/client allowlist | logout 철회가 SQLite 재시작 뒤 유지되고 미철회 세션은 보존됨 |
| offline result import | bearer-authenticated sanitized result + evidence digest | bad token/digest rejected; accepted result replaces verdict/findings and regenerates correlation warning/recommendations |
| UI terminal snapshot guard | delayed evidence/messages completion and conversation switch | terminal run/evidence/messages are committed together; stale delayed snapshot produces no commit |

## 2026-10-10 execution record

- Commit: `eadba3075074d1a3e726f553f38345a705695c02`
- Environment: Windows, Python 3.12.14, Node.js 22.18.0, npm 10.9.3
- Provider: `mock`; model calls and token usage were zero
- Local transport: `function` through `DirectToolClient`; target HTTP used in-process `ASGITransport`
- The repository `.venv` could not start because its recorded base Python installation no longer existed. Validation used a separate disposable Python 3.12 environment installed from `requirements-full.lock`; the broken repository environment was not overwritten.

| Mode | Command | Run ID | HTTP / tools / evidence | Offline correlation | Verdict |
|---|---|---|---|---|---|
| vulnerable | `python scripts/run_local_core.py --mode vulnerable` | `local-vulnerable-4343327e3ec0` | 11 / 12 / 5 | 5/5 | `VULNERABLE` |
| fixed | `python scripts/run_local_core.py --mode fixed` | `local-fixed-712a8c2cbf05` | 11 / 12 / 5 | 5/5 | `BLOCKED_BY_ACCESS_CONTROL` |

Each local run was evaluated immediately, before starting the other mode, with `python -m verifier.cli evaluate --run-dir reports/runs/<run_id> --local-evidence data/target-<mode>.sqlite3`. The generated `report.json`, `report.md`, `evidence.json`, `offline_verification.json`, target SQLite files, virtual environments, frontend dependencies, and build output are gitignored runtime artifacts.

The MCP Host result uses a TestClient request whose Host header is the documented VM address. It proves the application allowlist behavior, not connectivity to an actual VM. The loopback MCP integration starts a real Uvicorn socket and uses the Agents SDK `MCPServerStreamableHttp` client, while its synthetic target remains in-process ASGI.

## User-reported three-VM verification — 2026-10-14

The following results are transcribed from the attached verification guide, which states that it was prepared from the user's VM terminal output, offline-verification JSON, and web UI observation. Those underlying terminal captures, JSON files, and UI captures were not attached for direct inspection in this task. Codex did not execute commands in the VMs. The four run directories and VM SQLite files were not present in this Windows checkout, so their file contents and existence were not independently inspected here. The exact commit executed in the VMs is not confirmed; `6e9f4f5` was the reviewed Windows `main` before this documentation update and must not be treated as proof of the VM execution commit.

- Environment reported by the user: VirtualBox controller/worker/target VMs, Ubuntu 26.04.1 LTS, project Python 3.12.15
- Scope: registered target `lab-web`, published `access-control` scenario, synthetic data, provider `mock`
- Topology: controller `10.77.0.10` / `192.168.56.10`, worker `10.77.0.20` / `10.78.0.20`, target `10.78.0.30`
- Each combination was run once. These four runs are functional examples, not repeatability, detection-rate, or model-quality measurements.

| Target mode | Transport | Run ID | Offline verdict | Evidence / correlation | UI result |
|---|---|---|---|---|---|
| vulnerable | function | `run_9a446c4d55464f75b834becc747144c0` | `VULNERABLE` | 5 / 5 | imported and observed |
| vulnerable | MCP | `run_00d1dddd988049a09e64783d8b4d886a` | `VULNERABLE` | 5 / 5 | imported and observed |
| fixed | function | `run_e859f540f64245e3acc16a2ccb1d9985` | `BLOCKED_BY_ACCESS_CONTROL` | 5 / 5 | imported and observed |
| fixed | MCP | `run_367d971796d8484db0441d251d1d293c` | `BLOCKED_BY_ACCESS_CONTROL` | 5 / 5 | imported and observed; last result remained visible after restart |

All four offline JSON results were reported with an empty `warnings` array. The online socket-separated runs first remained `INCONCLUSIVE` / `offline-pending`; final verdicts were produced by comparing target-local observations and then manually importing only the sanitized result. This is not an online automatic-correlation result. The vulnerable runs reportedly completed the user-b control request and then exposed user-b's exact synthetic private marker to user-a. The fixed runs reportedly completed the same control request and denied user-a access to that resource.

The user also reported these point-in-time health checks using `curl --noproxy '*' --connect-timeout 3 --max-time 5`:

| Source | Destination | Reported observation | Narrow conclusion |
|---|---|---|---|
| controller | `10.77.0.20:9000/health` | `status=ok`, phase 1, Nmap/Playwright `not_implemented` | worker health endpoint responded |
| worker | `10.78.0.30:8080/health` | `status=ok`, mode `fixed`, data `synthetic-only` | target health endpoint responded |
| controller | `10.78.0.30:8080/health` | curl error 28 after about 3 seconds | this direct attempt did not receive a response |

The timeout alone does not prove that UFW caused the block or establish complete isolation. Routing, firewall counters, IPv6, alternate protocols, external egress, and service-to-service authentication were not comprehensively verified by these three health requests. Shared clipboard was used to move sanitized evidence, so clipboard isolation is not claimed.

## Not verified

- Independent Codex reproduction or file-level inspection of the user-reported VM runs, and the exact commit executed in those VMs
- Complete NIC/routing/forwarding/firewall rule and counter audit, IPv6 and alternate-protocol paths, external egress, and every negative network path
- real OpenAI API call, account model access, output quality, retries, token usage, cost, and latency
- automated browser behavior for login, provider selection, refresh, conversation switching, cancellation, SSE reconnect/polling, visual layout, or screenshots; the user reported only manual UI import and restart persistence observations
- Nmap installation/execution and Playwright browser/egress enforcement
- TLS/mTLS, multiple controller processes/users, long-duration load, and memory behavior
- repeated VM runs, detection-rate statistics, tampered-result rejection, and bad-token rejection in the actual VM environment

## Interpretation limit

These results cover one registered synthetic access-control fixture. They do not measure generalized vulnerability discovery, autonomous penetration testing, production readiness, complete network isolation, model performance, or a 100% detection rate. Mock provider calls are not local or live LLM results. The 2026-10-10 local core record remains separate from the user-reported 2026-10-14 VM record. A socket-separated `COMPLETED` workflow may remain `INCONCLUSIVE` until target-local observations are correlated offline.
