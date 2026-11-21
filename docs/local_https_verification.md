# 운영자 등록 로컬 HTTPS API 지원

등록된 IP literal HTTPS origin과 Worker 전용 CA bundle을 사용해 기존 `preview → 계획 확인 → run → 저장 증거 재판정`을 실행한다. 인증서 체인·유효기간·접속 IP SAN 검증을 유지한다. 대상은 기존 독립 첨부파일 API이며 새 API를 만들지 않았다. 기능 범위는 **로컬 HTTPS 대상 지원**이다. DNS/외부 서비스/실전 버그 바운티 지원을 뜻하지 않는다.

시작 시 원격 main은 `17d72b8`, PR #1/#2는 미병합이었다. 검토 완료 `codex/independent-api-validation / 7f2c324`에서 `codex/local-https-verification`을 만들었다. Draft PR은 선행 #2 브랜치를 base로 한다. main 병합·VM 배포·기존 VM 설정 변경은 수행하지 않는다.

## 처음 확인한 제약과 최소 변경

1. `TargetPolicy`가 http만 허용했고 registry 기본 port도 80으로 고정돼 있었다. 정확한 http/https IP origin을 허용하고 HTTPS 기본 port 443, IPv6 literal bracket 직렬화를 처리했다. DNS, userinfo, query, fragment, origin 경로는 계속 거절한다.
2. Worker HTTP client는 전용 trust 설정을 받지 않았다. `worker/tls.py`에 운영자 CA를 한 번 읽어 SSLContext에 적재하는 기능을 추가하고 기존 공통 client 경로에 연결했다. HTTP transport나 접근 통제 verifier를 새로 만들지 않았다.
3. 기존 정책 snapshot에는 TLS trust 식별값이 없었다. HTTPS에서만 버전이 명시된 `tls` 메타데이터를 snapshot 입력 및 공개 policy record에 포함한다. 기존 HTTP fingerprint·plan digest·보고서 직렬화는 그대로 유지한다.
4. 기존 인증서 실패는 일반 transport 실패였다. SSL 검증 오류의 구조화된 코드만 매핑해 정제된 TLS reason과 INCONCLUSIVE를 남긴다. 예외 원문이나 CA 경로를 보고하지 않는다.

## 운영자 설정과 신뢰 경계

기존 운영자 registry의 origin을 실제 승인 IP/port의 `https://<IP>:<port>`로 정확히 등록한다. 어댑터 경로·계정·리소스는 기존 방식대로 별도 scope와 일치해야 한다. 이번 구현은 저장소의 운영 `config/targets*.json`을 바꾸지 않는다.

Worker 전용 환경파일의 새 설정은 `TARGET_CA_BUNDLE`이다. 값은 해당 Worker가 읽을 수 있는 전용 PEM CA 파일이다. 예시의 경로는 실제 배포값이 아니다.

```dotenv
TARGET_REGISTRY_PATH=<operator-registry-path>
TARGET_BASE_URL=https://<registered-IP>:<port>
TARGET_CA_BUNDLE=<operator-owned-ca-bundle-path>
```

`TARGET_BASE_URL`은 registry와의 동등성 검사이며 override가 아니다. HTTP 대상은 CA 설정을 비워 둔다. HTTPS인데 CA가 없거나 파일이 잘못됐으면 Worker 시작/check를 거절한다. Controller/Target 환경에는 CA 설정을 넣지 않는다. 모델/function/MCP step 입력에 URL·CA 경로·verify 옵션을 추가하지 않았다.

`common.service_config check/serve worker`와 `worker.cli check-policy`, Worker factory가 같은 trust 바인딩을 사용한다. 로컬 테스트는 실제 Worker service에 동일한 바인딩을 사용하고, factory/서비스별 설정 경로도 별도 회귀로 검증한다. Controller→Worker의 function/MCP 연결은 기존 HTTP 제어 경로이며 **이번 TLS 지원은 Worker→등록 Target 구간**이다.

신뢰 설정은 다음과 같이 고정한다.

- `SSLContext(PROTOCOL_TLS_CLIENT)`, `CERT_REQUIRED`, `check_hostname=True`, CN fallback 해제, 최소 TLS 1.2, strict X.509 검증과 trusted-first chain 처리. 시스템 default CA 로딩 함수를 호출하지 않고 전용 bundle을 명시적으로 적재한다. proxy/SSL 관련 환경변수도 `trust_env=False`로 사용하지 않는다.
- bundle은 시작 때 PEM CA만 포함하는지, CA로 적재되는지, 유효기간이 현재 시각에 맞는지 확인한다. 개인키·leaf-only·빈 파일·잘못된 PEM을 거절한다. CA를 찾지 못해 다른 저장소로 fallback하지 않는다.
- `ca_bundle_sha256`는 **실제로 적재한 파일 bytes**의 SHA-256이다. 파일명/경로가 같아도 내용이 달라지면 다른 신뢰 설정이다. 내용이 같고 경로만 다르면 동일하다.
- `context_ca_sha256`는 실제 SSLContext의 CA DER 집합을 정규화한 hash다. Python runtime이 추가한 인증서 기록까지 식별하며 임의로 새 trust를 덧붙이는 경우도 감지한다. TLS 검증 방식은 `dedicated-ca-ip-san-v1`로 명시한다. hash는 식별 정보이며 서명이 아니다.
- CA 파일은 자동 재로딩하지 않는다. snapshot 조회와 매 HTTP 전송 전 파일 내용·context trust 집합·검증 옵션이 고정값과 같은지 확인한다. 변경/삭제 시 `TLS_TRUST_CHANGED_RESTART_REQUIRED` 등으로 거절한다. 파일 확인 직후 바뀌더라도 실제 연결은 이미 적재한 고정 context를 사용하며 새 신뢰를 조용히 적용하지 않는다.
- 변경 적용은 **Worker 재시작 → 새 preview → 새 digest 명시 확인 → run**이다. 이전 plan을 새 Worker에 보내면 policy mismatch로 첫 Target 요청 전에 거절한다. 실행 중 이미 확보한 scope를 새 CA 정책으로 바꾸지 않는다.

사용한 Codex Python runtime의 SSLContext 생성자는 기본 CA 기록 1개를 추가한다. 로컬 runtime 소스를 확인했으며 이는 특정 root를 거부하기 위한 기록이다. 이 runtime 동작을 우회하거나 제거하지 않는다. 그 기록도 실제 context hash에 포함한다. 다른 Python runtime에서는 context hash가 다를 수 있으므로 Worker가 반환한 snapshot을 확인해야 한다. 시스템 전역 trust store를 변경하거나 추가 CA로 재시도한 것은 아니다.

## 호환성과 증거

`operator-resource-v1` 흐름과 기존 evidence/report 형식은 유지한다. HTTPS policy record에만 `tls.verification`, 두 trust hash, minimum_version이 추가되며 그 내용이 snapshot SHA-256에 들어간다. HTTP에서는 optional tls 필드를 직렬화에서 **아예 생략**하므로 예전 HTTP snapshot 입력을 바꾸지 않는다. HTTPS 계약에는 TLS identity가 반드시 있어야 한다. 예전 클라이언트가 새 HTTPS 메타데이터를 이해하지 못하면 업데이트가 필요하며, 필드를 제거해 우회하지 않는다.

기존 HTTP profile의 고정 hash와 11월 13일의 16개 plan digest 및 저장된 14개 run replay 호환을 회귀로 확인한다. 이전 파일을 다시 쓰지 않는다. TLS는 transport/policy 경계이고 접근 통제 판정기는 기존 정제 관찰만 사용한다. 대상 모드, 서버 내부 모델/로그, 기대 verdict, handshake 계수는 verifier 입력이 아니다.

## 실제 로컬 TLS 검증

```powershell
.\.venv\Scripts\python.exe -m scripts.run_local_https_verification --output verification_tmp/local-https-new
.\.venv\Scripts\python.exe -m pytest
```

frontend 디렉터리에서 `npm run build`를 실행한다. 실제 실행 커밋/환경/결과는 [2026-11-14 보고서](../reports/local_https_verification_20261114/README.md)를 따른다. output은 새 폴더여야 한다.

기존 `AttachmentService`에 서버 TLS socket만 추가한다. 실행마다 임시 CA·서버 키/인증서를 생성하고 정상 leaf에 실제 접속 IP `127.0.0.1` SAN을 넣는다. 잘못된 SAN 시험은 CN이 올바른 IP여도 SAN이 다르면 거절되는지 확인한다. 개인키는 제한된 임시 디렉터리에만 저장한다(Windows: 현재 사용자 전용 ACL, POSIX: 디렉터리 0700/키 0600). 종료 후 해당 디렉터리가 제거됐는지 확인한다. CA private key는 디스크에 저장하지 않는다. 기준 UTC 시각과 leaf 유효기간을 기록하고 시스템 시각은 바꾸지 않는다.

인증서 생성은 개발용 `cryptography==50.0.2`를 사용한다. 기존 전체 lockfile에 이미 고정·설치돼 있는 버전을 dev extras와 requirements-dev에 명시했다. production TLS 검증은 표준 라이브러리 ssl이며 새로운 runtime 패키지는 필요하지 않다. 전체 lockfile이나 VM 의존성을 변경하지 않는다.

| 행렬 | 기준 |
|---|---|
| 취약/수정 × cookie/Bearer × function/MCP, 정상 8건 | preview Target HTTP 0, run HTTP 11/tools 12/evidence 11, 취약 VULNERABLE·수정 BLOCKED_BY_ACCESS_CONTROL, replay 일치 |
| 미신뢰 CA/다른 IP SAN/만료 leaf × cookie function/MCP, 6건 | 실제 TCP/TLS handshake 시도, 업무 HTTP handler 0, FAILED/INCONCLUSIVE와 정제 TLS reason |
| 같은 CA 경로의 내용 교체·Worker 재시작 × function/MCP, 2건 | 이전 plan은 target TCP/HTTP 0으로 policy mismatch 거절; 새 preview와 digest run은 정상 완료 |

CA rotation 시험의 새 유효 bundle은 원래 CA와 새 CA를 함께 포함한다. 신뢰 집합과 hash는 바뀌지만 원래 서버는 새 신뢰 집합에서도 유효하므로, 새 preview 승인 후 정상 연결까지 확인할 수 있다. 다른 경로에 같은 내용을 둔 경우 identity가 같은지도 별도 회귀로 검증한다.

## 오류와 측정 경계

오류 원문 대신 `TLS_CERT_UNTRUSTED`, `TLS_CERT_IP_SAN_MISMATCH`, `TLS_CERT_EXPIRED`, `TLS_CERT_NOT_YET_VALID`, `TLS_CERT_VERIFY_FAILED`, `TLS_HANDSHAKE_FAILED`를 사용한다. 체인 검증 실패 시 HTTP로 바꾸거나 다른 CA/context로 재시도하지 않는다. 기존 redirect 거절도 유지한다.

`tcp_accepted`, TLS handshake 시도/성공/실패, HTTP handler 실제 수신을 별도로 기록한다. TLS 실패에서 HTTP 0은 **네트워크 시도 0이 아니다**. 기존 Worker의 `limits_used.http_requests`는 전송 전에 소비하는 요청 예산이므로 실패한 첫 TLS 시도에서도 1이다. Target HTTP 0, Worker 요청 예산 1/tools 1, 증거 0을 그대로 보고하며 사용량을 0으로 바꿔 맞추지 않는다. FAILED run은 replay에서도 INCONCLUSIVE다. Controller 정책 조회와 MCP handshake는 Target 요청 수에 포함하지 않는다.

정상 11개 관찰과 scope/plan/claim/run 연결, 저장 증거 replay를 보존한다. 비밀번호·cookie/token·초기/변경 proof·개인키 전체 및 key base64 조각·임시 CA 경로를 공개 산출물과 대조한 뒤 복사한다. 인증서 공개 identity/hash만 남기고 key·인증정보·로컬 경로·오류 원문은 내보내지 않는다.

## 완료 범위

완료 기준은 HTTP 호환, 정상 TLS 8건, 잘못된 인증서 6건 거절, CA 변경 계획 거절 및 새 승인 실행, fallback/검증 해제 없음, replay·비밀값 검사 통과다. 이를 충족하면 **운영자 등록 로컬 HTTPS 지원을 완료**로 정리한다.

DNS/도메인·DNS rebinding, 외부 인터넷 서비스, SSO/OAuth/CSRF, 브라우저/Nmap/Playwright, 새 취약점, 유료 모델, VM 배포/방화벽 변경은 제외한다. 실제 TLS 행렬은 IPv4 loopback이며 IPv6는 origin 형식 회귀만 포함한다. 온라인 revocation/OCSP나 조직 PKI 운영까지 보장하는 기능은 아니다. 기능 완료 후 추가 fixture나 같은 행렬의 반복을 자동 후속 과제로 제안하지 않는다.
