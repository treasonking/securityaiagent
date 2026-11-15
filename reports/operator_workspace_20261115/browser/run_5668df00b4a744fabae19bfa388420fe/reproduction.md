# 접근 통제 재현 보고서 run_5668df00b4a744fabae19bfa388420fe

## 1. 검사 요약과 판정

COMPLETED / VULNERABLE

사유: CROSS_ACCOUNT_PRIVATE_PROOF · 계정 A의 교차 요청에서 준비된 비공개 리소스 B의 합성 proof가 일치했습니다.

## 2. 대상·관측 시각·범위

lab-web · https://attachments.securityai.test:50893

2026-11-15T10:09:47.029740+00:00 → 2026-11-15T10:09:47.806961+00:00

정책: `{"profile_id": "local-project-attachments", "revision": 1, "snapshot_sha256": "d754d2031654787c677316e6c12f7ab0cd47361eaa3083478af14ca5542f154d", "effective_limits": {"max_requests": 11, "max_tool_calls": 12, "timeout_seconds": 5.0, "run_timeout_seconds": 180.0, "max_response_bytes": 65536, "requests_per_second": 1000.0, "max_concurrency": 1, "max_runs": 100, "state_ttl_seconds": 600.0}, "tls": {"verification": "dedicated-ca-dns-san-v1", "ca_bundle_sha256": "d1153c257e5661621a7fcf7fe2857d515150a7329900e926f9052cdd05aacd54", "context_ca_sha256": "9ade64a6e117e76e61a2e34ed2e23af921f86d37edcfb2ea305c3e79dfefd7f7", "minimum_version": "TLSv1.2"}, "domain": {"version": "domain-network-v1", "allowed_ip_ranges": ["127.0.0.1/32"], "allow_non_global": true, "resolver": "system-a-aaaa-all-v1", "connection": "numeric-peer-checked-per-request-v1", "hostname": "attachments.securityai.test", "port": 50893}}`

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

계정 A의 교차 요청에서 준비된 비공개 리소스 B의 합성 proof가 일치했습니다.

실제 Worker 사용량: {'http_requests': 11, 'tool_calls': 12}; 최대 한도는 위 정책 참조. HTTP budget은 실제 수신 횟수와 다를 수 있습니다.

## 6. 근거 evidence와 정제 관측

- `6742e37be4385b96ce557a596703bd2e9c29dad02aaf0382c458a30826f84ddf`: user-a POST `/gateway/authenticate` → 200 / LOGIN_ESTABLISHED
- `73c5abb764335f7c59436a594f46c1d61728de058fdcc06b41dcf088b58448ec`: user-b POST `/gateway/authenticate` → 200 / LOGIN_ESTABLISHED
- `06698b9f95f15d98b891d30dc8be44b960b3f7f77c6d2d4328921650bdff40ae`: user-a GET `/gateway/session/profile` → 200 / IDENTITY_OBSERVED
- `2f5bd20834d1eb96e88170d2dedf5a1e84ec1f5ff34e2d03d771dd08d3bfe3be`: user-b GET `/gateway/session/profile` → 200 / IDENTITY_OBSERVED
- `06ffe53b9a6eea9ffec05732d425c6e339ca9d0cad60c57ff0d74278f0d973fb`: user-a GET `/workspace/attachments/attachment_M4s8` → 200 / PRIVATE_RESOURCE_OBSERVED
- `21802b5a5b7fc8dbac7e21e861a495edfdd1aba4f378fcff741634726a5049c6`: user-b GET `/workspace/attachments/attachment_N9t2` → 200 / PRIVATE_RESOURCE_OBSERVED
- `86f78913bf7a245dfd6fce260587414d1d80e08ab57766b0838ea83b8a810a04`: user-a GET `/workspace/attachments/attachment_N9t2` → 200 / PRIVATE_RESOURCE_OBSERVED
- `1c2f31db0582449d8b7425917bbb0530a3ae48fb31c2b250a891f48491f5e41f`: user-b GET `/workspace/attachments/attachment_N9t2` → 200 / PRIVATE_RESOURCE_OBSERVED
- `06956d53b4f82e0313faad2075d1facd6b4955f41519775f8b2a0732b979c2bc`: user-a GET `/workspace/attachments/attachment_M4s8` → 200 / PRIVATE_RESOURCE_OBSERVED
- `679b6cd813fca41ad78078c3eebb19de49ce9bab9e86d10d10fad2a02fd1a675`: user-a GET `/gateway/session/profile` → 200 / IDENTITY_OBSERVED
- `84486b38df166975f891c18fa538d8d334ae6939eeb355ef88bc9a42aa5cf0ef`: user-b GET `/gateway/session/profile` → 200 / IDENTITY_OBSERVED

DNS/TLS 관측(접근 통제 판정 입력 아님):

```json
[
  {
    "version": "domain-connection-v1",
    "origin": "https://attachments.securityai.test:50893",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 50893,
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
    "origin": "https://attachments.securityai.test:50893",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 50893,
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
    "origin": "https://attachments.securityai.test:50893",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 50893,
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
    "origin": "https://attachments.securityai.test:50893",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 50893,
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
    "origin": "https://attachments.securityai.test:50893",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 50893,
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
    "origin": "https://attachments.securityai.test:50893",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 50893,
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
    "origin": "https://attachments.securityai.test:50893",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 50893,
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
    "origin": "https://attachments.securityai.test:50893",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 50893,
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
    "origin": "https://attachments.securityai.test:50893",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 50893,
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
    "origin": "https://attachments.securityai.test:50893",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 50893,
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
    "origin": "https://attachments.securityai.test:50893",
    "dns_results": [
      "127.0.0.1"
    ],
    "selected_ip": "127.0.0.1",
    "peer_ip": "127.0.0.1",
    "peer_port": 50893,
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

계정 A의 교차 요청에서 준비된 비공개 리소스 B의 합성 proof가 일치했습니다.

두 준비 계정·두 리소스·해당 관측 시각에 한정합니다. 실제 고객 정보 유출, 금전 피해, 심각도 또는 사이트 전체 안전성을 주장하지 않습니다.

## 8. 수정 권고

서버에서 매 리소스 요청의 인증 주체와 소유권/프로젝트 권한을 검사하고 명시적으로 거절하세요.

## 9. 재판정과 실행 버전

{"replay": {"verdict": "VULNERABLE", "reason_code": "CROSS_ACCOUNT_PRIVATE_PROOF", "run_id": "run_5668df00b4a744fabae19bfa388420fe", "verdict_matches": true, "evidence_count": 11}, "version": {"workspace": "operator-workspace-v1", "component": "Controller", "commit": "8aff74fcbe76a61055bbb8a8f30c1776f0b1599c", "working_tree_dirty": true, "workspace_source_sha256": "a102890442a088e8cdca8b104a60753601a0bac55d452bbfa8977f4f93fb9e84"}}

원본 증거를 수정하지 않고 만든 파생 보고서입니다.
