# SecurityLab run run_2ac82f15ce0f46dea94dd11a4e8471a6

- Scenario: `access-control-http`
- Scope policy: `lab-records-access-control` revision `1`; SHA-256 `2b1da1e1dc1ffa0e8fcd18e887938e242fe74320cb5ee8c3cbb51876ce45beec`; limits `{'max_requests': 9, 'max_tool_calls': 10, 'timeout_seconds': 5.0, 'run_timeout_seconds': 180.0, 'max_response_bytes': 65536, 'requests_per_second': 2.0, 'max_concurrency': 1, 'max_runs': 100, 'state_ttl_seconds': 600.0}`
- Verification basis: `http_observation`
- Target: `lab-web`
- Mode: `unknown`
- Provider: `mock`
- Tool transport: `mcp`
- Status: `COMPLETED`
- Verdict: **VULNERABLE**

## Verified findings

- `cross_account_document_access`: **VULNERABLE** — Independent authenticated sessions and owner controls show the same private canary in user-a's cross-account response.

## Warnings and limits

- Limited to these synthetic accounts, resource, and observation time; not a site-wide safety claim.

This report contains synthetic markers and redacted metadata only. It does not include cookies, passwords, API keys, worker tokens, or full response bodies.