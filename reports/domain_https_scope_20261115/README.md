# Registered domain HTTPS scope — 2026-11-15 KST

The existing operator-resource verifier now runs against the registered `attachments.securityai.test` HTTPS origin with a dedicated CA, complete DNS answer-set scope checks and an actual socket pinned to a checked IP. SNI, certificate DNS SAN validation and HTTP Host retain the registered domain. This is registered-domain connectivity/scope support, not arbitrary website exploration or external bug-bounty readiness.

The previous PRs #1–#3 were open/unmerged at task start; remote main was `17d72b8`. Work started from reviewed `codex/local-https-verification / 6e40d9d` on `codex/domain-https-scope`. The follow-up Draft PR is based on `codex/local-https-verification`; no main merge or VM deployment was performed.

## Recorded execution

- Actual matrix code: `0bb9e58139e969d42289003a4ccfce8fb5b77326`, clean working tree at start. Implementation commit `20aee1e` preceded the source-manifest privacy correction in `0bb9e58`.
- Start: **2026-11-15 02:09:38 KST** (`2026-11-14T17:09:38.077831+00:00`). Duration: **32.266 seconds**.
- Environment: Python 3.12.14, Windows 10 build 19045, OpenSSL 3.5.8; HTTPX 0.28.1, HTTPCore 1.0.9. Provider: mock, no paid model calls.
- Exact matrix command: `.\.venv\Scripts\python.exe -m scripts.run_domain_https_verification --output verification_tmp/domain-https-publish-20261115-final`.
- Existing independent project-attachment API and certificate generator reused. Temporary CA/server certificates carry a DNS SAN. No new API/fixture, TargetStore, target DB, canary helper or internal answer marker was introduced.
- `matrix.json` records every run/plan digest, Worker scope, TLS verification method and CA fingerprints, source-byte hashes, actual network counters, expected versus actual verdict and replay. All **28 source hashes match both the executed commit and working files**.

Every integration DNS answer was injected through a test-only resolver. A guard rejected unexpected OS hostname lookups; there were **0**. Target TCP/TLS and function/MCP were actual loopback connections. This is not a live external DNS integration claim.

## Actual TLS matrix

All **24 combinations passed**. Each row below includes both function and MCP; the normal row also includes cookie/Bearer and vulnerable/fixed modes. Counts are **per run**, not cumulative totals. Every original and fresh preview had DNS/TCP/TLS/HTTP counts **0**.

| Case | Combinations | Actual TCP accept | TLS complete / fail | Actual Target HTTP | Worker HTTP budget / tools | Evidence | Outcome |
|---|---:|---:|---:|---:|---:|---:|---|
| Normal vulnerable/fixed × cookie/Bearer | 8 | 11 | 11 / 0 | 11 | 11 / 12 | 11 | VULNERABLE / BLOCKED_BY_ACCESS_CONTROL, respectively |
| DNS only outside approved range | 2 | 0 | 0 / 0 | 0 | 1 / 1 | 0 | FAILED / INCONCLUSIVE; DNS_ADDRESS_OUT_OF_SCOPE |
| DNS approved + unapproved mix | 2 | 0 | 0 / 0 | 0 | 1 / 1 | 0 | FAILED / INCONCLUSIVE; DNS_ADDRESS_OUT_OF_SCOPE |
| Empty DNS result | 2 | 0 | 0 / 0 | 0 | 1 / 1 | 0 | FAILED / INCONCLUSIVE; DNS_NO_RESULTS |
| Resolver raises failure | 2 | 0 | 0 / 0 | 0 | 1 / 1 | 0 | FAILED / INCONCLUSIVE; DNS_LOOKUP_FAILED |
| Trusted CA, wrong domain SAN | 2 | 1 | 0 / 1 | 0 | 1 / 1 | 0 | FAILED / INCONCLUSIVE; TLS_CERT_DOMAIN_MISMATCH |
| First DNS approved, next connection unapproved | 2 | 1 | 1 / 0 | 1 | 2 / 2 | 1 | First login reached Target; second connection blocked at DNS, INCONCLUSIVE |
| Redirect to unapproved origin | 2 | 1 | 1 / 0 | 1 | 1 / 1 | 0 | Existing redirect rejection; no destination lookup/connect, INCONCLUSIVE |
| Changed approved ranges; fresh approval after old plan rejection | 2 | 11 | 11 / 0 | 11 | 11 / 12 | 11 | Old plan rejected before run; fresh plan VULNERABLE |

The wrong-domain certificate kept the **correct CN** and a different DNS SAN: CN fallback did not bypass SAN validation. Its HTTP 0 means no handler received a request, **not** no network attempt. DNS-rejected runs truly had no Target TCP connection. Worker budget increments happen before DNS/TCP/TLS and are not a measurement of delivered HTTP.

In each range-change case the Worker was restarted with a separate registry allowing an additional explicit IP. The Controller's previous registry/plan was preserved. The old plan received `WORKER_POLICY_CHANGED`, had no run directory or claim, and produced DNS/TCP/TLS/HTTP **0**. A new registry-matching preview and explicit digest confirmation then completed 11/12/11. The `policy_change.json` file distinguishes rejection from the later new run.

All normal connections returned the complete normalized answer `127.0.0.1`, selected that IP and verified the actual peer IP/port. The Target recorded the registered domain in both SNI and Host. No client-internal hostname lookup occurred. New connections rechecked DNS; no persistent connection or IP answer became an authority grant.

There are **26 issued plans, 24 claimed plans and 24 saved runs**. Every run's plan digest and expected/actual Worker snapshot match. All **24 saved-evidence replays match the original verdict**. Incomplete runs replay INCONCLUSIVE with INCOMPLETE_WORKFLOW; DNS/TLS failure details remain in the report and separate connection observation, not reconstructed from empty/partial access-control evidence.

## Implementation and regression scope

- Existing adapter configuration, account/resource contract and fixed read sequence are reused. No target-specific access-control verifier branch was added; verifier source is unchanged.
- `domain-network-v1` is optional for old origins and mandatory for DNS HTTPS. Ranges, non-global permission, hostname/port and fixed DNS/connection strategy participate in the snapshot. `dedicated-ca-dns-san-v1` distinguishes DNS SAN checks from old IP SAN metadata.
- The implementation uses public HTTPX custom transport and HTTPCore network backend/pool interfaces, plus public asyncio socket/stream/TLS APIs. No third-party private API patching. HTTPCore 1.0.9 was already in the full lock and is now explicitly a direct dependency.
- Regressions cover normalization/equivalent ranges, invalid origins, `/0` including collapsed unions, non-global flags, IPv4/IPv6/mapped/scoped addresses, DNS timeout, actual peer checking, deterministic selection/no retries, and CA drift between TCP and TLS socket cleanup.
- A single actual TLS request with a resolver whose **second answer is unapproved** still uses only the first checked result; the resolver was called once. Caller SNI override extensions do not alter the registered SNI/Host.
- Peer-mismatch rejection is tested through numeric peer-comparison units and a deliberately injected mismatch after an actual local TCP connection. It is a simulated mismatch, not a claim of observed real-world rebinding/routing tampering.
- Additional component TLS tests reject untrusted CA and expired domain certificates. Existing IP HTTPS 16-case tests and HTTP scenarios remain in the full suite.
- The OS resolver adapter is unit-tested with a stubbed `getaddrinfo` boundary: AF_UNSPEC, SOCK_STREAM, IPPROTO_TCP, flags 0, A/AAAA collection and scoped-result rejection. No live OS hostname resolution/external DNS claim is made.
- Stored preexisting HTTP and IP HTTPS plan digests and saved-run replays remain valid. No old report/evidence was overwritten. Optional domain fields are omitted for existing policies.

## Public evidence and provenance

Each case scans its public artifacts against generated passwords, sessions/tokens, raw proofs, private key full/fragment encodings and private certificate paths before publication. **430 per-case secret/key/path representations checked; 0 matches**. This sum includes repeat categories across independent cases, not 430 distinct secret types. All **24 temporary certificate/key directories were removed**. On this host, Windows current-user-only directory ACLs were used. System trust, hosts, DNS settings and time were not modified.

The final matrix's source paths are repository-relative; its source hashes were checked against Git and disk. A separate publication audit rejects absolute user paths and private-key PEM markers. `SHA256SUMS.json` covers the final report files and source provenance checks are recorded in `verification_summary.json`.

An initial 24-case matrix also passed, but a publication audit found an absolute repository path in its source-hash manifest. It remained in ignored `verification_tmp` and was not published. The manifest was fixed, a regression was added, and the final matrix was rerun from clean `0bb9e58`. The first full suite (collected before that new regression) passed 909 tests; the final full-suite result and build are recorded below and in the summary. Test expectations were not weakened to fit implementation results.

## Boundaries and completion

Actual socket/TLS coverage is **IPv4 loopback**. IPv6 has format/range/peer tests only. DNS values were test-injected; external DNS, OS DNS caching/TTL/CNAME infrastructure behavior, live external services and DNSSEC are unverified. OS getaddrinfo work already running in an executor can outlive cancellation, but its late result cannot connect the Target. No DNS/connection observation alone can produce an access-control verdict.

No existing environment files, DB, VM, firewall, deployment registry, system DNS/hosts or global CA store were changed. No VM deployment, main merge, browser test, Nmap/Playwright, SSO/OAuth/CSRF or paid model run was performed. Controller→Worker transport remains HTTP. Online revocation/OCSP and general PKI operations are outside this scope.

The stage is complete when the final verification summary marks all required checks passed. The next recommended action is review of this Draft PR and evidence. No new fixture or repetition of this same matrix is proposed as another stage.

Implementation, policy rules and reproduction details: [docs/domain_https_scope.md](../../docs/domain_https_scope.md).

## Final completion result

**Registered-domain HTTPS scope support is complete.** All completion conditions are true in `verification_summary.json`.

- Final full `.\.venv\Scripts\python.exe -m pytest`: **910 passed, 40 warnings, 296.53 seconds, exit 0**; includes 85 new domain regressions and existing HTTP/IP HTTPS scenarios. Warnings are the existing Pydantic/MCP deprecations and pytest cache-write permission warning.
- `npm run build` in `frontend`: **exit 0, 18 modules, 480ms**. Frontend source is unchanged; no browser validation is claimed.
- Final matrix: **24/24**; generated secret/key/path comparisons **430**, matches **0**; key directories removed **24/24**; replay **24/24**.
- No executable source changes after the final full-suite pass. Only documentation, sanitized reports and their byte-preservation attributes were finalized. The full suite was not repeated after this final pass.
