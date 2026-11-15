# 접근 통제 재현 보고서 run_9e640307aad243a89c11c6261002d5a3

## 1. 검사 요약과 판정

COMPLETED / BLOCKED_BY_ACCESS_CONTROL

사유: EXPLICIT_DENIAL_WITH_STABLE_CONTROLS · 관측한 교차 요청은 명시적으로 거절됐습니다.

## 2. 대상·관측 시각·범위

lab-web · https://attachments.securityai.test:56292

2026-11-15T10:19:58.143468+00:00 → 2026-11-15T10:20:02.442466+00:00

정책: `{"profile_id": "local-project-attachments", "revision": 1, "snapshot_sha256": "9e4612cf7efe67b94c84939ff5fd9f8f82d8032d1749e38f6eeed806147af18f", "effective_limits": {"max_requests": 11, "max_tool_calls": 12, "timeout_seconds": 5.0, "run_timeout_seconds": 180.0, "max_response_bytes": 65536, "requests_per_second": 1000.0, "max_concurrency": 1, "max_runs": 100, "state_ttl_seconds": 600.0}, "tls": {"verification": "dedicated-ca-dns-san-v1", "ca_bundle_sha256": "43363b26d11e9b04cab7bd28bc1bbd21c2a628254ffc721c17ed7dbc9524e69d", "context_ca_sha256": "574b8074b895748016abdea7095e71af2c8f58b639897fb6633b4ebf41542cab", "minimum_version": "TLSv1.2"}, "domain": {"version": "domain-network-v1", "allowed_ip_ranges": ["127.0.0.1/32"], "allow_non_global": true, "resolver": "system-a-aaaa-all-v1", "connection": "numeric-peer-checked-per-request-v1", "hostname": "attachments.securityai.test", "port": 56292}}`

## 3. 계정·리소스 준비

서버 측 등록 프로필의 두 계정과 소유 리소스만 사용합니다. 인증정보는 운영자가 별도로 준비합니다.

{"user-a": "<ACCOUNT_A_LOGIN> / <ACCOUNT_A_PASSWORD>", "user-b": "<ACCOUNT_B_LOGIN> / <ACCOUNT_B_PASSWORD>", "session": "<COOKIE_OR_BEARER_FROM_LOGIN>"}

## 4. 요청 순서와 재현 절차

등록 프로필 선택 → 새 preview → 아래 순서·정책 확인 → 현재 digest 명시적 승인 → 실행 → 저장 증거 재판정. 임의 URL이나 경로를 추가하지 않습니다.

1. user-a · POST `/gateway/authenticate`
2. user-b · POST `/gateway/authenticate`
3. user-a · GET `/gateway/session/profile`
4. user-b · GET `/gateway/session/profile`
5. user-a · GET `/workspace/attachments/attachment_M4s8`
6. user-b · GET `/workspace/attachments/attachment_N9t2`
7. user-a · GET `/workspace/attachments/attachment_N9t2`
8. user-b · GET `/workspace/attachments/attachment_N9t2`
9. user-a · GET `/workspace/attachments/attachment_M4s8`
10. user-a · GET `/gateway/session/profile`
11. user-b · GET `/gateway/session/profile`

## 5. 기대 접근 통제와 실제 관측

소유자 요청은 성공하고 다른 계정의 비공개 리소스 요청은 거절돼야 합니다.

관측한 교차 요청은 명시적으로 거절됐습니다.

실제 Worker 사용량: {'http_requests': 11, 'tool_calls': 12}; 최대 한도는 위 정책 참조. HTTP budget은 실제 수신 횟수와 다를 수 있습니다.

## 6. 근거 evidence와 정제 관측

- `ee3fffb946b6637b8a04467cdedb28fd13af64bd193c2eb14070e6ffbbd16a9f`: user-a POST `/gateway/authenticate` → 200 / LOGIN_ESTABLISHED
- `d3f85dbe3cf0e6a6e080791f7a7aecf50cc5c5aac1d6ab9b1d082ff169685248`: user-b POST `/gateway/authenticate` → 200 / LOGIN_ESTABLISHED
- `79845eb092271f13a877de51f1f52dcb67d82322ea540decdd2ab1fcdbba8ab5`: user-a GET `/gateway/session/profile` → 200 / IDENTITY_OBSERVED
- `ec2671104cf31a2e41881366eba7d40fd801a2a53f566548783b75b499ea32f8`: user-b GET `/gateway/session/profile` → 200 / IDENTITY_OBSERVED
- `35031d703b2b9f5fa71c640b2fc4165a2433652319f3a7f336cfee1d30c2fdb7`: user-a GET `/workspace/attachments/attachment_M4s8` → 200 / PRIVATE_RESOURCE_OBSERVED
- `79eabd613fc5376e0ca838877dd032c22e1dda5e18ec7603705a20d9bf9f8abf`: user-b GET `/workspace/attachments/attachment_N9t2` → 200 / PRIVATE_RESOURCE_OBSERVED
- `1283b226a5d78a00d11c6b80c1c2dbea81b809d17355c5994de1554a2738aa76`: user-a GET `/workspace/attachments/attachment_N9t2` → 403 / EXPLICIT_RESOURCE_DENIAL
- `a4b99cb258bf1760b2cc50a5b9dd52322eb8179b47584c43faffa4f30b55fdad`: user-b GET `/workspace/attachments/attachment_N9t2` → 200 / PRIVATE_RESOURCE_OBSERVED
- `8549e4563ac4628e6e70847b35e3475aebaa2a3980c6cb54f80306ff0afb67b3`: user-a GET `/workspace/attachments/attachment_M4s8` → 200 / PRIVATE_RESOURCE_OBSERVED
- `1b1b6fd45f972fbd432a044673ca81f8523d7ef534bdbf0d9454f43fd531b614`: user-a GET `/gateway/session/profile` → 200 / IDENTITY_OBSERVED
- `e2ba7eec2640c8943ac0a7350c9d046e0b23321938cefd95c618cdff4a37fc96`: user-b GET `/gateway/session/profile` → 200 / IDENTITY_OBSERVED

DNS/TLS 관측(접근 통제 판정 입력 아님):

```json
[
  {
    "version": "domain-connection-v1",
    "origin": "https://attachments.securityai.test:56292",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 56292,
    "peer_verified": true,
    "tls_server_name": "attachments.securityai.test",
    "stage": "complete",
    "reason_code": null,
    "tcp_attempts": 1,
    "tls_attempts": 1,
    "http_response_received": true
  },
  {
    "version": "domain-connection-v1",
    "origin": "https://attachments.securityai.test:56292",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 56292,
    "peer_verified": true,
    "tls_server_name": "attachments.securityai.test",
    "stage": "complete",
    "reason_code": null,
    "tcp_attempts": 1,
    "tls_attempts": 1,
    "http_response_received": true
  },
  {
    "version": "domain-connection-v1",
    "origin": "https://attachments.securityai.test:56292",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 56292,
    "peer_verified": true,
    "tls_server_name": "attachments.securityai.test",
    "stage": "complete",
    "reason_code": null,
    "tcp_attempts": 1,
    "tls_attempts": 1,
    "http_response_received": true
  },
  {
    "version": "domain-connection-v1",
    "origin": "https://attachments.securityai.test:56292",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 56292,
    "peer_verified": true,
    "tls_server_name": "attachments.securityai.test",
    "stage": "complete",
    "reason_code": null,
    "tcp_attempts": 1,
    "tls_attempts": 1,
    "http_response_received": true
  },
  {
    "version": "domain-connection-v1",
    "origin": "https://attachments.securityai.test:56292",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 56292,
    "peer_verified": true,
    "tls_server_name": "attachments.securityai.test",
    "stage": "complete",
    "reason_code": null,
    "tcp_attempts": 1,
    "tls_attempts": 1,
    "http_response_received": true
  },
  {
    "version": "domain-connection-v1",
    "origin": "https://attachments.securityai.test:56292",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 56292,
    "peer_verified": true,
    "tls_server_name": "attachments.securityai.test",
    "stage": "complete",
    "reason_code": null,
    "tcp_attempts": 1,
    "tls_attempts": 1,
    "http_response_received": true
  },
  {
    "version": "domain-connection-v1",
    "origin": "https://attachments.securityai.test:56292",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 56292,
    "peer_verified": true,
    "tls_server_name": "attachments.securityai.test",
    "stage": "complete",
    "reason_code": null,
    "tcp_attempts": 1,
    "tls_attempts": 1,
    "http_response_received": true
  },
  {
    "version": "domain-connection-v1",
    "origin": "https://attachments.securityai.test:56292",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 56292,
    "peer_verified": true,
    "tls_server_name": "attachments.securityai.test",
    "stage": "complete",
    "reason_code": null,
    "tcp_attempts": 1,
    "tls_attempts": 1,
    "http_response_received": true
  },
  {
    "version": "domain-connection-v1",
    "origin": "https://attachments.securityai.test:56292",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 56292,
    "peer_verified": true,
    "tls_server_name": "attachments.securityai.test",
    "stage": "complete",
    "reason_code": null,
    "tcp_attempts": 1,
    "tls_attempts": 1,
    "http_response_received": true
  },
  {
    "version": "domain-connection-v1",
    "origin": "https://attachments.securityai.test:56292",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 56292,
    "peer_verified": true,
    "tls_server_name": "attachments.securityai.test",
    "stage": "complete",
    "reason_code": null,
    "tcp_attempts": 1,
    "tls_attempts": 1,
    "http_response_received": true
  },
  {
    "version": "domain-connection-v1",
    "origin": "https://attachments.securityai.test:56292",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 56292,
    "peer_verified": true,
    "tls_server_name": "attachments.securityai.test",
    "stage": "complete",
    "reason_code": null,
    "tcp_attempts": 1,
    "tls_attempts": 1,
    "http_response_received": true
  }
]
```

## 7. 확인된 영향과 해석의 한계

관측한 교차 요청은 명시적으로 거절됐습니다.

두 준비 계정·두 리소스·해당 관측 시각에 한정합니다. 실제 고객 정보 유출, 금전 피해, 심각도 또는 사이트 전체 안전성을 주장하지 않습니다.

## 8. 수정 권고

서버에서 매 리소스 요청의 인증 주체와 소유권/프로젝트 권한을 검사하고 명시적으로 거절하세요.

## 9. 재판정과 실행 버전

{"replay": {"verdict": "BLOCKED_BY_ACCESS_CONTROL", "reason_code": "EXPLICIT_DENIAL_WITH_STABLE_CONTROLS", "run_id": "run_9e640307aad243a89c11c6261002d5a3", "verdict_matches": true, "evidence_count": 11}, "version": {"workspace": "operator-workspace-v1", "component": "Controller", "commit": "8aff74fcbe76a61055bbb8a8f30c1776f0b1599c", "working_tree_dirty": true, "workspace_source_sha256": "a102890442a088e8cdca8b104a60753601a0bac55d452bbfa8977f4f93fb9e84"}}

원본 증거를 수정하지 않고 만든 파생 보고서입니다.
