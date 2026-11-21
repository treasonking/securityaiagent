# SecurityLab run adapter-bd71682d64b044e7ad9ed303abea5e23

- Scenario: `access-control-http`
- Scope policy: `lab-access-control` revision `4`; SHA-256 `11787107219266452dd93c4d08d9864bd4c68e3929a7764749607580d1164a25`; limits `{'max_requests': 2, 'max_tool_calls': 10, 'timeout_seconds': 5.0, 'run_timeout_seconds': 180.0, 'max_response_bytes': 65536, 'requests_per_second': 2.0, 'max_concurrency': 1, 'max_runs': 100, 'state_ttl_seconds': 600.0}`
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