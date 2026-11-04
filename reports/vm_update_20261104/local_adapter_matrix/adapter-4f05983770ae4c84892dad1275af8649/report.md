# SecurityLab run adapter-4f05983770ae4c84892dad1275af8649

- Scenario: `access-control-http`
- Scope policy: `lab-access-control` revision `4`; SHA-256 `9459dbff742df07635abd57219d083545a8f786a3da1ccf7fba3318a527856d3`; limits `{'max_requests': 2, 'max_tool_calls': 10, 'timeout_seconds': 5.0, 'run_timeout_seconds': 180.0, 'max_response_bytes': 65536, 'requests_per_second': 2.0, 'max_concurrency': 1, 'max_runs': 100, 'state_ttl_seconds': 600.0}`
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