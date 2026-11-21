# 로컬 HTTPS 지원 — 실제 TLS 검증 결과

**운영자가 등록한 IP HTTPS API에 인증서 검증을 유지한 채 기존 preview → 계획 확인 → run → 증거 재판정을 적용했다.** 정상 8조합, 잘못된 인증서 6건, 같은 CA 경로의 내용 교체 후 이전 plan 거절 및 새 승인 실행 2건이 기준을 충족했다. 기존 독립 첨부파일 API를 재사용했으며 새 fixture/API는 만들지 않았다.

기준은 `7f2c324fcf8e32f9287d6861147e89fa8f4e261f`, 실제 실행 코드 커밋은 **`c9b3a33a3b47736f95f3bc23091cccc5903c633d`**다. PR #1/#2는 시작 시 미병합이고 main은 `17d72b8`이었다. 새 브랜치는 `codex/local-https-verification`이다. 실행은 2026-11-14 **15:21:05 KST / 06:21:05 UTC**, 25.641초였다. Python 3.12.14, Windows 10, OpenSSL 3.5.8 환경이다. 시계를 변경하지 않았고 각 인증서의 기준 시각·유효기간도 case 결과에 남겼다.

실제 명령:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_local_https_verification --output verification_tmp/local-https-publish-20261114
.\.venv\Scripts\python.exe -m pytest
# frontend 디렉터리
npm run build
```

[matrix.json](matrix.json)은 실행 시 `working_tree_dirty=true`를 기록했으며 이를 수정하지 않았다. Git 상태에 보였던 두 파일은 비교 시 HEAD/index/working-tree byte가 같았고 내용 diff가 없었다. **기록된 모든 실행 source SHA-256은 실행 커밋의 Git blob 및 실제 파일과 일치함을 별도로 확인**했다. clean 실행으로 소급 표시하지 않는다. 이후 변경은 문서와 정제 증거 보존 설정이다.

## 정상 HTTPS 8조합

각 행은 preview 동안 Target TCP/TLS/HTTP 증가 **0**, run 동안 검증된 TLS handshake **11회**, 실제 HTTP 수신 **11회**, Worker HTTP 예산 **11회**·도구 **12회**, 정제 증거 **11개**다. plan/snapshot/claim/run 연결과 저장 증거 재판정이 일치했다.

| 인증 | 모드 | 전송 | 실제 판정 | 정제 결과 |
|---|---|---|---|---|
| cookie | 취약 | function | VULNERABLE | [결과](cookie-vulnerable-function-normal/result.json) |
| cookie | 취약 | MCP | VULNERABLE | [결과](cookie-vulnerable-mcp-normal/result.json) |
| cookie | 수정 | function | BLOCKED_BY_ACCESS_CONTROL | [결과](cookie-fixed-function-normal/result.json) |
| cookie | 수정 | MCP | BLOCKED_BY_ACCESS_CONTROL | [결과](cookie-fixed-mcp-normal/result.json) |
| Bearer | 취약 | function | VULNERABLE | [결과](bearer-vulnerable-function-normal/result.json) |
| Bearer | 취약 | MCP | VULNERABLE | [결과](bearer-vulnerable-mcp-normal/result.json) |
| Bearer | 수정 | function | BLOCKED_BY_ACCESS_CONTROL | [결과](bearer-fixed-function-normal/result.json) |
| Bearer | 수정 | MCP | BLOCKED_BY_ACCESS_CONTROL | [결과](bearer-fixed-mcp-normal/result.json) |

Target 구간은 실제 SSL socket이다. function/MCP는 실제 TCP Worker 연결을 사용하며 ASGI 직접 호출로 대체하지 않았다. Controller→Worker는 기존 HTTP 제어 경로다. Target의 HTTP/1.0 응답 특성상 이 시험에서는 요청마다 새 TLS 연결을 만들었다. TLS 연결 재사용 성능을 측정한 것은 아니다.

## 잘못된 인증서 6건

| 조건 | function | MCP | 정제 reason |
|---|---|---|---|
| 서버 발급 CA를 신뢰하지 않음 | [결과](cookie-vulnerable-function-untrusted_ca/result.json) | [결과](cookie-vulnerable-mcp-untrusted_ca/result.json) | TLS_CERT_UNTRUSTED |
| 접속 IP 127.0.0.1과 다른 SAN 127.0.0.2 | [결과](cookie-vulnerable-function-wrong_san/result.json) | [결과](cookie-vulnerable-mcp-wrong_san/result.json) | TLS_CERT_IP_SAN_MISMATCH |
| 만료된 leaf 인증서 | [결과](cookie-vulnerable-function-expired/result.json) | [결과](cookie-vulnerable-mcp-expired/result.json) | TLS_CERT_EXPIRED |

모든 행에서 실제 Target TCP accept **1**, TLS handshake 시도/실패 **1/1**, handshake 성공 **0**, HTTP handler 수신 **0**이다. 인증된 업무 요청은 도달하지 않았다. IP SAN 오류의 CN은 접속 IP와 같지만 SAN 불일치를 거절했다. 만료된 leaf는 생성 기준 시각보다 1시간 전에 만료되도록 만들었고 시스템 시간을 바꾸지 않았다.

실행 보고서는 모두 **FAILED / INCONCLUSIVE**, Worker 요청 예산 1·도구 1·증거 0이다. Worker가 전송 전에 예산을 소비하므로 TLS 실패의 요청 예산을 0으로 조작하지 않는다. HTTP handler 0을 네트워크 시도 없음이라고 해석하지 않는다. HTTP fallback·다른 CA 재시도·검증 해제는 없었다. 정상 TLS handshake가 아닌 인증서 검증 단계에서 실패했다.

FAILED 저장 run의 replay는 기존 규칙에 따라 INCONCLUSIVE / INCOMPLETE_WORKFLOW다. **판정이 최초 보고서와 일치**하며, replay가 빈 HTTP 증거로 특정 TLS 오류를 다시 증명하는 것은 아니다. 원래 정제 TLS 사유는 report/result에 보존했다. 예외 원문·CA 로컬 경로는 공개하지 않는다.

## CA 변경과 새 preview

cookie [function](cookie-vulnerable-function-ca_rotation/ca_rotation.json), [MCP](cookie-vulnerable-mcp-ca_rotation/ca_rotation.json)에서 다음을 실제 실행했다.

1. CA A를 사용하는 Worker에서 preview를 발급했다. Target HTTP/TCP 0.
2. Worker를 종료하고 **같은 파일 경로의 CA 내용을 A+B로 교체**, 새 Worker를 같은 자체 확보 port에 기동했다. A+B는 다른 유효한 trust 집합이며 원래 서버도 검증할 수 있다.
3. 이전 plan을 실행하자 `WORKER_POLICY_CHANGED`로 거절했다. 그 구간 Target TCP/TLS/HTTP 증가 **모두 0**, 이전 plan의 claimed 없음.
4. 새 policy snapshot을 읽는 새 preview를 발급하고, 새 plan digest를 명시해 별도 run을 실행했다. HTTP 11/tools 12/evidence 11, VULNERABLE, replay 일치.

두 trust hash와 snapshot SHA-256이 실제로 달라졌고 새 plan ID/digest를 보존했다. 파일 경로만 비교하지 않는다. 별도 회귀에서는 같은 내용/다른 경로의 identity 일치, 실행 중 CA 내용 변경 뒤 다음 HTTP 전송 전 거절, 고정 SSLContext가 파일을 자동 재로딩하지 않음도 확인했다. 마지막 회귀는 service 직접 호출 + 실제 Target TLS 시험이며 전체 function/MCP TCP 행렬과 구분한다.

총 **issued 18개, claimed 16개, 저장 run 16개**다. 정상/rotation 성공 10개와 인증서 실패 6개를 모두 보존했다. 회수 후 16개 저장 run을 다시 replay해 판정 일치를 확인했다. 정책 사전 거절 2건은 새 run ID를 만들지 않았다.

## Trust 설정과 기존 HTTP 호환

Worker 전용 `TARGET_CA_BUNDLE`을 시작 시 읽어 고정 context에 적재한다. CA 파일 bytes의 `ca_bundle_sha256`, 실제 context CA DER 집합의 `context_ca_sha256`, `dedicated-ca-ip-san-v1` 검증 방식 및 TLS 최소 1.2를 HTTPS policy snapshot과 report에 포함한다. `CERT_REQUIRED`, hostname/IP SAN 확인, CN fallback 해제, strict chain 검증을 유지한다. 파일 변화는 자동 적용하지 않으며 재시작과 새 preview가 필요하다.

이 Python runtime의 SSLContext 생성자는 특정 root를 거부하는 CA 기록 1개를 추가한다. 초기 엄격한 CA 집합 동등 검사에서 이를 발견했다. 이 runtime 거부 설정을 우회하지 않고, 제공 CA가 실제 CA로 적재됐는지 검사하면서 context 전체의 identity도 별도로 고정하도록 구현했다. 시스템 default CA 로딩이나 전역 trust store 변경은 없다. 잘못된 CA·SAN·유효기간은 실제 handshake에서 거절됐다.

기존 HTTP snapshot에는 TLS 필드를 직렬화하지 않는다. 고정된 기존 HTTP snapshot hash와 11월 13일 저장 plan 16개 digest·run 14개 replay 호환을 검증했다. 이전 기록을 새 형식으로 다시 쓰지 않았다. 접근 통제 verifier 자체에는 수정이 없고, 대상 모드·내부 상태·기대값·TCP/TLS 계수도 입력하지 않는다.

초기 집중 회귀에서 기존 “HTTPS IP 자체를 거절”하는 테스트 1개가 새 요구와 충돌했다. HTTPS DNS 거절로 해당 입력을 바꾸고, HTTPS IP는 등록 가능하되 CA 없이는 Worker 시작이 거절되는 새 검증을 추가했다. 인증서 행렬의 기대 결과를 구현 결과에 맞춰 바꾼 것은 아니다. 그 이후 집중 202개가 통과했다.

## 비밀값·개인키·보존

비밀번호·proof·cookie/Bearer token·Worker token은 매번 생성해 메모리에만 보유한다. CA private key는 디스크에 저장하지 않고 server key만 Windows 현재 사용자 전용 ACL 임시 폴더에 저장했다. 16건 모두 종료 후 key 폴더 제거를 확인했다. POSIX 경로는 0700/0600을 설정하도록 구현했지만 이번 실제 실행은 Windows다.

공개 전 산출물을 **비밀값·개인키 전체/부분·private 경로 표현 총 292개**와 대조해 일치 0건을 확인했다. 각 case의 publication_check를 보존한다. JSON으로 escape한 개인키를 일부러 쓰는 회귀도 공개 전에 거절됐다. 공개 파일에는 CA fingerprint, 인증서 유효기간/IP SAN, run/plan 식별값과 정제 관찰만 있고 원본 응답·인증정보·개인키·원본 서버 로그는 없다.

기존 환경파일/DB/VM/방화벽/공유 폴더·운영 registry·시스템 전역 CA를 변경하지 않았다. 이전 보고서는 그대로 보존했다. 개발 인증서 생성용 cryptography는 기존 full lockfile의 50.0.2를 dev dependency로 명시했으며 full lockfile/VM 의존성은 바꾸지 않았다.

## 완료 범위와 한계

신규 TLS 회귀 26개를 포함한 전체 pytest는 **825 passed, 28 warnings, 286.83초**였다. 집중 회귀는 202개 통과했고 frontend `npm run build`도 성공했다(18 modules, 737ms). 경고는 기존 Pydantic/MCP deprecation과 pytest cache 쓰기 제한이며 실패는 아니다. 전체 통과 후 실행 코드를 바꾸거나 동일 전체 테스트를 반복하지 않았다. 변경하지 않은 UI의 실제 브라우저 검증도 수행하지 않았다.

완료 조건: 기존 HTTP 호환, HTTPS 정상 8조합, 잘못된 인증서 3종×2 transport 거절, CA 변경 이전 계획 거절과 새 승인 실행, 검증 해제/HTTP fallback 없음, 저장 증거 판정 일치, 공개 비밀값 검사 **모두 충족**. [verification_summary.json](verification_summary.json)에 기계 판독 요약을 남겼다.

본 단계는 **운영자 등록 로컬 HTTPS API 지원**이다. HTTP 호환·정상 TLS·인증서 오류 거절·CA 변경 승인 경계·replay·공개 검사 결과를 근거로 판단한다. 테스트 개수만으로 기능 완료를 주장하지 않는다.

DNS/도메인, 외부 인터넷 서비스/실전 버그 바운티, SSO/OAuth/CSRF, UI 브라우저, Nmap/Playwright, 유료 모델, 실제 VM 배포·방화벽 변경은 제외했다. 실제 TLS 행렬은 IPv4 loopback이며 IPv6는 origin 형식 검사만 했다. 온라인 revocation/OCSP·장기 PKI 운영·성능 보장은 포함하지 않는다. 다음 권장 작업은 Draft PR의 변경·증거 검토이며, 추가 fixture나 동일 행렬 반복을 자동 후속 작업으로 제안하지 않는다.

자세한 설정·오류·재현 방법은 [운영 문서](../../docs/local_https_verification.md)를 참고한다.
