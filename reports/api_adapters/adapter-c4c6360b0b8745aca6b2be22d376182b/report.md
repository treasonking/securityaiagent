# SecurityLab run adapter-c4c6360b0b8745aca6b2be22d376182b

- Scenario: `access-control-http`
- Scope policy: `lab-records-access-control` revision `1`; SHA-256 `8aa61c3592a520ac01fa95c4d9a1c0be720ad914cfecb7545805041541cac42d`; limits `{'max_requests': 2, 'max_tool_calls': 10, 'timeout_seconds': 5.0, 'run_timeout_seconds': 180.0, 'max_response_bytes': 65536, 'requests_per_second': 2.0, 'max_concurrency': 1, 'max_runs': 100, 'state_ttl_seconds': 600.0}`
- Verification basis: `http_observation`
- Target: `lab-web`
- Mode: `unknown`
- Provider: `mock`
- Tool transport: `mcp`
- Status: `COMPLETED`
- Verdict: **INCONCLUSIVE**

## Verified findings

- No evidence-verified finding.

## Warnings and limits

- tool workflow incomplete: ToolExecutionError: list_own_documents(user-a): SCOPE_LIMIT_EXCEEDED: HTTP request limit exceeded
- HTTP scenario evidence is missing, duplicated, or out of sequence

This report contains synthetic markers and redacted metadata only. It does not include cookies, passwords, API keys, worker tokens, or full response bodies.