# Evidence index

2026-10-08 로컬 Windows 개발 환경 기준이다. VM 또는 live OpenAI evidence로 해석하지 않는다.

| Claim | Command / observation | Evidence path | Status | Limitation |
|---|---|---|---|---|
| vulnerable/fixed HTTP core and policy paths work | `.\.venv\Scripts\python.exe -m pytest` → `28 passed, 4 warnings` | `tests/test_target.py`, `tests/test_policy.py`, `tests/test_core_flow.py` | Verified locally | target runs in-process ASGI, not target VM |
| vulnerable and fixed reports reproduce separately | `scripts\run_local_core.py --mode vulnerable/fixed` + offline verifier | local gitignored run dirs; summary in `reports/current_verification.md` | Verified locally | functional fixture, not a general security metric |
| controller API, SQLite history, SSE, redaction work | same pytest run | `tests/test_controller_api.py`, `tests/test_repository.py` | Verified locally | single process/user only |
| SDK-managed Streamable HTTP MCP connects and calls shared tools | same pytest run | `tests/test_mcp_integration.py` | Verified on loopback | worker target transport remains in-process; no control-net evidence |
| React escapes output and uses controller same-origin API | `npm test` → `3 passed` | `frontend/tests/security-contract.test.mjs` | Verified statically | not a browser E2E test |
| production static UI builds | `npm run build` → success | `frontend/dist/` (gitignored build output) | Verified locally | visual/browser behavior not captured |
| OpenAI provider runs with a real model | not run | `controller/providers.py` | Not verified | no API key/model authorization supplied |
| VM isolation and resource allocation | not run | `docs/network_setup.md` | Not verified | requires user-owned VirtualBox VMs |
| Nmap / Playwright | intentionally not run | `docs/phase2_nmap_playwright.md` | Not implemented (phase 2) | no tool or dependency in v1 |

Python 경고 4건은 MCP/Agents SDK dependency 내부의 Pydantic forward-reference 경고 1건과 deprecated transport helper 경고 3건이다. 테스트 실패는 아니지만 dependency 업데이트 시 재확인이 필요하다.
