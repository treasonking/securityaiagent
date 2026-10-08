# Threat model

## Assets

- host/VM/network boundary
- model API key and worker token
- local application session and synthetic target sessions
- evidence integrity and separation from evaluator truth

## Threats and controls

| Threat | v1 control | Residual risk |
|---|---|---|
| Arbitrary target or SSRF | target ID registry, IP literal, exact scheme/host/port, no arbitrary URL tool | OS firewall/NIC rules still require VM verification |
| Encoded path/userinfo/IPv6 bypass | repeated decode checks, fixture document ID regex | future domain support needs DNS pinning design |
| Redirect escape | `follow_redirects=False`; any 3xx is policy failure | target may still return misleading non-redirect content |
| Proxy environment escape | worker HTTP client uses `trust_env=False` | OS routing/firewall remains the stronger boundary |
| Prompt injection in page | body never reaches model/UI/report; only allowlisted synthetic marker | new tools must preserve this transform |
| Credential/session leak | opaque `session_ref`, worker-injected credentials, recursive redaction, metadata-only DB/report | process memory still contains short-lived secrets |
| Infinite/expensive loop | fixed procedure, max model turns, cumulative worker request/time/size/rate limits, concurrency 1 | durable multi-process queues are not implemented |
| False security verdict | required successful controls, separate verifier, explicit INCONCLUSIVE errors | online target-log correlation may remain pending |
| Unauthorized worker access | source-address allowlist plus bearer token | TLS is absent on isolated v1 internal networks |
| Browser XSS | React escaped text, no raw HTML, CSP, same-origin API | no Playwright browser E2E until phase 2 |

외부 사이트, arbitrary shell, automatic patch/deploy, malware, persistence, credential theft, brute force, DoS, broad crawling, and multi-agent autonomy are out of scope.
