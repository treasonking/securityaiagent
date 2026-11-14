# Registered domain HTTPS and DNS/IP scope

An operator can register an exact ASCII HTTPS hostname, a dedicated Worker CA bundle and explicit IP ranges, then use the existing mock-only preview → review → digest-confirmed run → saved-evidence replay flow. This extends the previous IP HTTPS implementation; it does not authorize arbitrary sites or external testing.

## Registration and identity

Add `network` to the operator-owned schema 2.0 registry target, alongside the existing profile and adapter. The following is an illustrative **test-only** fragment, not a deployment registry change:

```json
{
  "origin": "https://attachments.securityai.test:18443",
  "network": {
    "version": "domain-network-v1",
    "allowed_ip_ranges": ["127.0.0.1/32"],
    "allow_non_global": true,
    "resolver": "system-a-aaaa-all-v1",
    "connection": "numeric-peer-checked-per-request-v1"
  }
}
```

The Worker still obtains `TARGET_REGISTRY_PATH` and `TARGET_CA_BUNDLE` from its service-specific operator environment, checked/launched with `common.service_config check/serve worker`. Existing environment files were not modified. Credentials/proof references, two registered accounts/resources and the fixed read flow remain unchanged. The model and function/MCP arguments cannot select an origin, DNS server, ranges, resolver implementation or CA/TLS option. A test resolver can only be injected by local test code, never by a registry value or environment switch.

Rules:

- HTTPS only for DNS names. ASCII labels are lowercased, 1–63 characters, alphanumeric with interior hyphens, at least two labels, total length at most 253. The existing resource-policy origin length limit (200) also applies. Trailing dots, wildcard/empty labels, Unicode and `xn--` IDN labels, underscores and ambiguous numeric hosts are rejected. A final label must contain a letter.
- The origin must have an explicit canonical port (1–65535), without path, userinfo, query or fragment, even an empty `?`/`#`. Host case normalizes consistently through registry, snapshot, SNI and Host. Existing IP literal origins retain their separate policy; a domain network field on an IP origin is rejected.
- Ranges are IP literals or CIDRs, normalized to networks, deduplicated, collapsed by address family and sorted. Host bits in CIDRs normalize to the corresponding network. Equivalent unions produce the same policy identity. Empty lists, more than 128 input ranges, `/0`, or a union collapsing to `/0` are rejected.
- `allow_non_global` defaults to false. Private, loopback and unscoped link-local addresses require **both** an explicit matching range and this true flag. Unspecified, multicast and reserved addresses remain denied (IPv6 loopback is explicitly handled). This flag never bypasses range membership.
- IPv4-mapped IPv6 and IPv6 scope identifiers are rejected in origins, ranges, DNS answers and peer checks. IPv6 networks overlapping the mapped-address block are rejected. Unscoped link-local addresses may be explicitly approved, but deployments that require a zone/interface identifier are unsupported; there is no fallback or scope guessing.

HTTPS domain snapshots include `domain-network-v1`, canonical hostname/port, normalized ranges, non-global permission and resolver/connection modes. TLS identity uses `dedicated-ca-dns-san-v1` plus the same actual CA-file/context-content hashes and minimum TLS version as IP HTTPS. CA files are validated/frozen at startup; bytes or trust/options changing in place require restart and a new preview.

Changing hostname/port, ranges, non-global permission or trust identity changes the snapshot. An old plan is rejected before claim/run/Target contact. The local registry inputs must also agree with the restarted Worker's policy before a new preview can be issued. DNS observations are **not** put into a permanent policy fingerprint or treated as new authority.

## Connection implementation

1. Preview only reads the authenticated Worker policy. It performs no Target DNS, TCP, TLS or HTTP operation.
2. Immediately before every new domain connection, the frozen CA configuration is checked. `SystemResolver` requests AF_UNSPEC/SOCK_STREAM/IPPROTO_TCP results with flags 0 via asyncio's OS `getaddrinfo` interface, including A/AAAA results supplied by the OS (no AI_ADDRCONFIG filtering).
3. All returned addresses are parsed, deduplicated and numerically sorted. Empty/failing resolution, malformed/scoped/mapped results, or more than 256 results are rejected. If **any** valid result is outside policy, none is connected.
4. The first approved numeric address is selected (IPv4 then IPv6, numeric order). A nonblocking socket of that family is connected to the numeric tuple. No hostname is passed to the connector; the connected socket is passed to `asyncio.open_connection(sock=...)`. There is no second hostname DNS lookup inside HTTPX/HTTPCore.
5. `getpeername()` must equal the checked IP and registered port before TLS/HTTP. The socket is upgraded using `StreamWriter.start_tls`, with the original registered hostname for SNI and certificate DNS SAN validation. The peer is checked again after TLS. HTTP Host retains that hostname and the nondefault port.
6. Each request uses its own client/connection, with zero idle keepalive connections and zero connection/address retries. A subsequent request re-enters the full resolver/IP check. DNS changes within the approved ranges are allowed; a newly out-of-range result stops that connection. No unbounded retry, HTTP fallback, CA fallback, proxy or redirect following exists.

Implementation uses the public [HTTPX custom transport API](https://www.python-httpx.org/advanced/transports/) and [HTTPCore network backend API](https://www.encode.io/httpcore/network-backends/) with its public `AsyncConnectionPool`, not patched private client fields or imports. Supported versions are HTTPX 0.28.1 and HTTPCore 1.0.9. HTTPCore was already in the full lock; it is now explicitly a direct dependency because the implementation uses its public types. Compatibility tests exercise those interfaces over actual TLS and verify versions. Python is the existing supported 3.12 series. Certificate generation reuses the existing cryptography development dependency.

Per-stage I/O timeouts and the existing enclosing request/run deadlines apply. An OS getaddrinfo operation already running in an executor may finish after cancellation; its late result cannot initiate a Target connection. The application does not configure OS DNS servers, caches or search suffixes. This is not DNSSEC validation or an independent authoritative DNS client.

## Failure and evidence boundaries

| Reason | Failure stage | Target effect |
|---|---|---|
| `DNS_LOOKUP_FAILED` | DNS failure/timeout | No socket connect |
| `DNS_NO_RESULTS` | DNS empty | No socket connect |
| `DNS_RESULT_INVALID` | Unsupported/malformed/oversized result | No socket connect |
| `DNS_ADDRESS_OUT_OF_SCOPE` | Full answer set validation | No socket connect for that request |
| `DNS_PEER_MISMATCH` | Connected peer check | Close socket before application HTTP; pre-TLS check normally stops before TLS |
| `TLS_CERT_DOMAIN_MISMATCH` | TLS DNS SAN validation | Handshake attempted, no application HTTP |
| Existing `TLS_CERT_UNTRUSTED`, `TLS_CERT_EXPIRED`, etc. | TLS verification | Handshake attempted, no application HTTP |
| `DOMAIN_CONNECTION_FAILED` | Other domain transport failure | Incomplete workflow, sanitized reason |
| `WORKER_POLICY_CHANGED` | Controller plan check | No run claim or Target connection |

Started incomplete runs are FAILED/INCONCLUSIVE; a rejected old plan is not represented as a run. Worker request budgets increment before DNS/TCP/TLS, so a blocked first attempt still consumes HTTP budget 1/tool 1 while the actual Target HTTP handler receives 0. A DNS change on the second request consumes 2/2 but receives only the first login HTTP request. The Target measurement and Worker budget are intentionally separate.

For domain runs, `ResourceResult` returns a bounded versioned `connection_observation`. The Controller stores these separately in `connection_observations.json`: registered origin, normalized DNS answers, selected/actual peer IP and port, peer match, TLS name, phase and attempt/response indicators. The plan/report's Worker snapshot supplies TLS verification method and CA fingerprints. Actual server TCP accept/TLS handshake/HTTP counters and observed SNI/Host are harness-only measurements. Server-side "handshake attempt" includes accepting a connection for TLS, even if the client closes before sending ClientHello; the Worker counters distinguish that case.

No DNS/connection counters, server state, mode or expected verdict are fed to `verify_operator`. The existing ResourceEvidence schema and access-control verifier remain unchanged. Replay uses only its existing contract/report/evidence; failed/partial runs replay INCONCLUSIVE, not a fresh proof of the particular DNS/TLS failure. Exception text, credential/session/token values, raw proof, response bodies, local CA paths and keys are not published.

HTTP and IP HTTPS omit the new optional fields, retain their original TLS identifiers and fingerprints, and keep old stored plan hashes/replays valid. Old reports are not rewritten. Domain policies require updated Worker and Controller models; older strict clients fail on the new fields rather than silently running without network authority.

## Reproduction and validated scope

```powershell
.\.venv\Scripts\python.exe -m scripts.run_domain_https_verification --output verification_tmp/domain-https-new-run
.\.venv\Scripts\python.exe -m pytest
cd frontend
npm run build
```

The script refuses an existing output destination. It reuses the existing project-attachment API, temporary CA/certificate tool, mock provider, two account/resource registry and preview/plan history helpers. The fixed `.test` hostname has a DNS SAN certificate; its resolver answers are injected and OS hostname resolution is blocked during the integration matrix. Target TLS and both function/MCP channels use actual loopback TCP. The wrong-SAN certificate deliberately keeps a matching CN so the test also proves CN fallback is disabled. Temporary key ACLs/permissions are restricted and cleanup is checked.

The 24 matrix combinations consist of 8 normal mode/auth/transport combinations plus outside-only DNS, mixed DNS, empty DNS, failed lookup, wrong DNS SAN, second-connection DNS change, redirect, and changed-range/new-preview cases on both transports. Normal flow remains 11 HTTP / 12 tools / 11 evidence. Tests also cover a second DNS answer becoming unapproved after the first check, numeric peer comparison and a simulated mismatch after real TCP, strict domain CA/expiry, CA drift between TCP and TLS cleanup, range normalization and IPv4/IPv6/mapped-address handling.

See the dated report for actual results, commands, source hashes, commit, environment and redaction counts. These are separate claims:

- **Actual socket/TLS:** IPv4 loopback Target TLS, SNI/Host, peer check, function/MCP and saved replay.
- **Injected DNS:** all integration domain answers; no external DNS requests. A peer mismatch is deliberately simulated in a regression after a real TCP connection, not claimed as naturally observed routing tampering.
- **OS resolver implementation:** unit tests verify getaddrinfo flags, both address families and scoped-result rejection with a stubbed OS-call boundary. Live OS hostname resolution, DNS infrastructure behavior/TTL/caching and DNSSEC are not verified.
- **IPv6:** format/range/peer-family tests only; no actual IPv6 socket/TLS claim in this execution.
- **Not performed:** VM deployment, external DNS/services, changes to environments/DB/firewall/hosts/system DNS/global CA, browser/SSO/OAuth/CSRF/Nmap/Playwright, paid models or main merge. Controller→Worker remains the existing HTTP control channel.

Completion of the stated checks completes registered-domain HTTPS scope support. The next action is review of the Draft PR and its evidence, not another fixture or the same validation repeated as a new stage.
