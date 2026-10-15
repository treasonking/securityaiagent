# SecurityLab run http-6198113e474341d7ba256f5ad1696381

- Scenario: `access-control-http`
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