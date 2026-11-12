# SecurityLab run adapter-afcea19213574608aab553e1d6f6ea76

- Scenario: `access-control-http`
- Scope policy: `lab-access-control` revision `4`; SHA-256 `5e051f8a5f7c72173d6816637fa3445d2e7fd025633684c6d68793e336359683`; limits `{'max_requests': 9, 'max_tool_calls': 10, 'timeout_seconds': 5.0, 'run_timeout_seconds': 180.0, 'max_response_bytes': 65536, 'requests_per_second': 2.0, 'max_concurrency': 1, 'max_runs': 100, 'state_ttl_seconds': 600.0}`
- Verification basis: `http_observation`
- Target: `lab-web`
- Mode: `unknown`
- Provider: `mock`
- Tool transport: `function`
- Status: `COMPLETED`
- Verdict: **VULNERABLE**

## Verified findings

- `cross_account_document_access`: **VULNERABLE** — Independent authenticated sessions and owner controls show the same private canary in user-a's cross-account response.

## Warnings and limits

- Limited to these synthetic accounts, resource, and observation time; not a site-wide safety claim.

This report contains synthetic markers and redacted metadata only. It does not include cookies, passwords, API keys, worker tokens, or full response bodies.