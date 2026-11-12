# SecurityLab run adapter-d316b2d5378d4ba29ec0bed69a7011f4

- Scenario: `access-control-http`
- Scope policy: `lab-records-access-control` revision `1`; SHA-256 `a2e78f1c0cbe72f6e4ac2d7ef5bd18b9a3b3f13a4e0d61e09b445ec7035fdc47`; limits `{'max_requests': 9, 'max_tool_calls': 10, 'timeout_seconds': 5.0, 'run_timeout_seconds': 180.0, 'max_response_bytes': 65536, 'requests_per_second': 2.0, 'max_concurrency': 1, 'max_runs': 100, 'state_ttl_seconds': 600.0}`
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