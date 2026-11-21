# SecurityLab run adapter-a5986c79a3ec40aea63dff50d464b3ac

- Scenario: `access-control-http`
- Scope policy: `lab-records-access-control` revision `1`; SHA-256 `55510ffcc690a758b74d67de169403f7781534cef2497804dc0d7180822a914d`; limits `{'max_requests': 9, 'max_tool_calls': 10, 'timeout_seconds': 5.0, 'run_timeout_seconds': 180.0, 'max_response_bytes': 65536, 'requests_per_second': 2.0, 'max_concurrency': 1, 'max_runs': 100, 'state_ttl_seconds': 600.0}`
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