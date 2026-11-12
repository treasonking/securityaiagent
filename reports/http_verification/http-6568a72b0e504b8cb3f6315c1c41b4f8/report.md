# SecurityLab run http-6568a72b0e504b8cb3f6315c1c41b4f8

- Scenario: `access-control-http`
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