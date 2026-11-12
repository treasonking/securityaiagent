# SecurityLab run adapter-f2f1634693fd47eaac9ae5665d50bb43

- Scenario: `access-control-http`
- Scope policy: `lab-access-control` revision `4`; SHA-256 `5a489f00e70cef09117d4731c64d40fd8ebe757495a8ddc342d6e07895ffbd4a`; limits `{'max_requests': 9, 'max_tool_calls': 10, 'timeout_seconds': 5.0, 'run_timeout_seconds': 180.0, 'max_response_bytes': 65536, 'requests_per_second': 2.0, 'max_concurrency': 1, 'max_runs': 100, 'state_ttl_seconds': 600.0}`
- Verification basis: `http_observation`
- Target: `lab-web`
- Mode: `unknown`
- Provider: `mock`
- Tool transport: `mcp`
- Status: `COMPLETED`
- Verdict: **BLOCKED_BY_ACCESS_CONTROL**

## Verified findings

- `cross_account_document_access`: **BLOCKED_BY_ACCESS_CONTROL** — The authenticated cross-account request was denied; owner and requester controls remained valid before and after it.

## Warnings and limits

- Limited to these synthetic accounts, resource, and observation time; not a site-wide safety claim.

This report contains synthetic markers and redacted metadata only. It does not include cookies, passwords, API keys, worker tokens, or full response bodies.