# SecurityLab run adapter-c2306f19ed73451fad3b36cdfa56f1f5

- Scenario: `access-control-http`
- Scope policy: `lab-access-control` revision `4`; SHA-256 `8da7379ee276a9b9c3bf94978fd0f9ec1be73569e4efabd34a41ed6462ced1d2`; limits `{'max_requests': 9, 'max_tool_calls': 10, 'timeout_seconds': 5.0, 'run_timeout_seconds': 180.0, 'max_response_bytes': 65536, 'requests_per_second': 2.0, 'max_concurrency': 1, 'max_runs': 100, 'state_ttl_seconds': 600.0}`
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

- tool workflow incomplete: ToolExecutionError: start_session(user-b): SCOPE_ACCOUNT_DENIED: account is outside the scope profile
- HTTP scenario evidence is missing, duplicated, or out of sequence

This report contains synthetic markers and redacted metadata only. It does not include cookies, passwords, API keys, worker tokens, or full response bodies.