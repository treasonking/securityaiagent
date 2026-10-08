# SecurityLab v1 local verification — 2026-10-08

## Verified locally

| Area | Command | Result |
|---|---|---|
| Python core/API/MCP | `.\.venv\Scripts\python.exe -m pytest` | 28 passed, 4 dependency warnings |
| React security contract | `npm test` | 3 passed |
| React production build | `npm run build` | success, 17 modules transformed |
| vulnerable fixture | `scripts\run_local_core.py --mode vulnerable` | `VULNERABLE`, 11 HTTP requests, 12 tool calls, 5 evidence items |
| fixed fixture | `scripts\run_local_core.py --mode fixed` | `BLOCKED_BY_ACCESS_CONTROL`, 11 HTTP requests, 12 tool calls, 5 evidence items |
| vulnerable offline correlation | `python -m verifier.cli evaluate ...target-vulnerable.sqlite3` | 5/5 evidence correlated, verdict reproduced |
| fixed offline correlation | `python -m verifier.cli evaluate ...target-fixed.sqlite3` | 5/5 evidence correlated, verdict reproduced |

The local run IDs were `local-vulnerable-a19553d6f2b9` and `local-fixed-a3abdebdfb4f`. Their generated directories and SQLite files are intentionally gitignored because they are runtime evidence, not source fixtures.

MCP validation started the worker as a real loopback Uvicorn server and used the OpenAI Agents SDK `MCPServerStreamableHttp` client. It checked connection, exact four-tool discovery, start/list/fetch calls, structured result schema, missing auth, unregistered target, cancellation rejection, and server-disconnected failure.

## Not verified

- VirtualBox VM creation, addresses, NIC roles, forwarding, firewall rules/counters, positive and negative network paths
- real OpenAI API call, account model access, model quality, token usage, cost, latency
- browser E2E, UI screenshots, Playwright egress enforcement
- Nmap installation or execution
- TLS/mTLS and multi-user/multi-process deployment

## Interpretation limit

These results reproduce one synthetic access-control fixture. They do not measure generalized vulnerability discovery, a production site's security, or model performance. Mock provider calls are recorded as zero model calls and are not a local LLM result.
