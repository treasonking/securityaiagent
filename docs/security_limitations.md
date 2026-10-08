# Security limitations

- 로컬 테스트는 ASGI synthetic target과 loopback Uvicorn MCP를 사용했다. 세 VM NIC·routing·firewall은 검증하지 않았다.
- OpenAI provider 경계는 구현했지만 API key/model 권한이 없어 live 호출·품질·비용·latency를 검증하지 않았다.
- UI는 TypeScript build와 정적 보안 계약 테스트만 수행했다. Playwright E2E, 스크린샷, 키보드/접근성, 브라우저별 검증은 2단계다.
- v1 worker 내부망은 bearer token + source IP allowlist이며 TLS/mTLS가 없다. 물리/가상 네트워크 격리가 전제다.
- controller job manager는 단일 프로세스·동시 실행 1이다. durable queue, multi-user tenancy, multiple Uvicorn workers를 지원하지 않는다.
- 취소는 새 worker 호출을 막고 반복을 정리하지만 이미 전송된 하나의 HTTP 요청을 원격 서버에서 되돌릴 수는 없다.
- 온라인 evidence의 target log correlation이 없으면 판정은 `INCONCLUSIVE`로 유지된다. 별도 verifier CLI로 target-local 관찰과 연결해야 한다.
- scrypt 설정과 synthetic credentials는 실습용이다. 실제 인증 서비스 설계·password rotation·account lockout 평가가 아니다.
- 하나의 IDOR 스타일 fixture만 있으므로 보안 일반화, 전체 취약점 탐지율, 실제 조직의 방어 수준을 주장할 수 없다.
- 현재는 기존 캡스톤 저장소 안의 독립 서브프로젝트다. 문서가 요구한 완전한 별도 저장소 분리는 아직 하지 않았다.

## Phase 2 only

Nmap은 `target_id + fixed profile_id`만 받는 inventory 도구로 설계해야 하며 arbitrary CIDR/NSE/shell은 금지한다. Playwright는 worker 전용 새 context, 동시성 1, service worker 차단, redirect/frame/subresource/XHR/WebSocket/download/popup 전부에 exact-origin 정책과 OS firewall을 함께 적용해야 한다. v1에는 두 도구의 실행 코드나 dependencies가 없다.
