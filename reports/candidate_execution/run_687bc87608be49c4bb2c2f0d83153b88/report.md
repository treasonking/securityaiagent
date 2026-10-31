# SecurityLab run run_687bc87608be49c4bb2c2f0d83153b88

- Scenario: `access-control-http`
- Scope policy: `lab-access-control` revision `4`; SHA-256 `9e7fd58626e67486e48864b704b4f51e49cc7d9238aa20d5f09b1034e0de9f12`; limits `{'max_requests': 9, 'max_tool_calls': 10, 'timeout_seconds': 5.0, 'run_timeout_seconds': 180.0, 'max_response_bytes': 65536, 'requests_per_second': 2.0, 'max_concurrency': 1, 'max_runs': 100, 'state_ttl_seconds': 600.0}`
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