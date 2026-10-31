# SecurityLab run run_cefb6dc2667c4498b7d8cb5a6564b3cd

- Scenario: `access-control-http`
- Scope policy: `lab-records-access-control` revision `1`; SHA-256 `b601a7caf7d0cde12ce688d189bcb98d240efda6d9d2f5a0af280d68476be8de`; limits `{'max_requests': 9, 'max_tool_calls': 10, 'timeout_seconds': 5.0, 'run_timeout_seconds': 180.0, 'max_response_bytes': 65536, 'requests_per_second': 2.0, 'max_concurrency': 1, 'max_runs': 100, 'state_ttl_seconds': 600.0}`
- Verification basis: `http_observation`
- Target: `lab-web`
- Mode: `unknown`
- Provider: `mock`
- Tool transport: `function`
- Status: `COMPLETED`
- Verdict: **BLOCKED_BY_ACCESS_CONTROL**

## Verified findings

- `cross_account_document_access`: **BLOCKED_BY_ACCESS_CONTROL** — The authenticated cross-account request was denied; owner and requester controls remained valid before and after it.

## Warnings and limits

- Limited to these synthetic accounts, resource, and observation time; not a site-wide safety claim.

This report contains synthetic markers and redacted metadata only. It does not include cookies, passwords, API keys, worker tokens, or full response bodies.