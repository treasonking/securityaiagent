# Security limitations

- 로컬 테스트는 ASGI synthetic target과 loopback Uvicorn MCP를 사용했다. 세 VM NIC·routing·firewall은 검증하지 않았다.
- OpenAI provider 경계는 구현했지만 API key/model 권한이 없어 live 호출·품질·비용·latency를 검증하지 않았다.
- `MODEL_MAX_CALLS`는 현재 Agents SDK의 `max_turns`로 전달되며 결제·retry·token의 엄밀한 hard cap이 아니다. provider가 응답 전에 실패하면 실제 실패 비용/usage가 완전하게 남는다고 보장하지 않는다.
- 현재 provider는 `scenario_id`와 `target_id`로 후보만 생성한다. 사용자 자유문을 모델 계획에 전달하지 않으며 모델이 도구나 실행 순서를 선택하지 않는다. 이는 의도한 고정 시나리오 경계이며 범용 agent 기능이 아니다.
- UI는 TypeScript build와 정적 상태/보안 계약 테스트만 수행했다. 로그인·provider 선택·새로고침·대화 전환·SSE 단절 복구의 실제 브라우저 E2E, 스크린샷, 키보드/접근성, 브라우저별 검증은 하지 않았다.
- v1 worker 내부망은 bearer token + source IP allowlist이며 TLS/mTLS가 없다. 물리/가상 네트워크 격리가 전제다.
- controller job manager와 세션 폐기 목록은 단일 프로세스 상태다. durable queue, multi-user tenancy, multiple Uvicorn workers를 지원하지 않는다.
- 취소는 rate-limit/semaphore 대기를 깨우고 진행 중 HTTP coroutine을 취소한다. 이미 target이 완전히 처리한 요청의 서버측 효과를 되돌리는 트랜잭션 보장은 아니다.
- 온라인 evidence의 target log correlation이 없으면 판정은 `INCONCLUSIVE`로 유지된다. 별도 verifier CLI로 target-local 관찰과 연결해야 한다.
- 오프라인 반영 endpoint는 별도 bearer token과 evidence identity digest를 검사하지만 네트워크 TLS를 자체 제공하지 않는다. 격리망 또는 TLS reverse proxy와 안전한 토큰 배포가 필요하다.
- scrypt 설정과 synthetic credentials는 실습용이다. 실제 인증 서비스 설계·password rotation·account lockout 평가가 아니다.
- 하나의 IDOR 스타일 fixture만 있으므로 보안 일반화, 전체 취약점 탐지율, 실제 조직의 방어 수준을 주장할 수 없다.
- synthetic target은 JSON 로그인/문서 API와 최소 소개 HTML만 제공하며 실제 업무 사이트 수준의 화면·브라우저 동작을 재현하지 않는다.
- UI 접근 인증은 로컬 단일 사용자용 초기 공유 토큰이다. 외부 IdP, 계정별 권한, brute-force lockout, 중앙 세션 폐기를 제공하지 않는다.

## Phase 2 only

Nmap은 `target_id + fixed profile_id`만 받는 inventory 도구로 설계해야 하며 arbitrary CIDR/NSE/shell은 금지한다. Playwright는 worker 전용 새 context, 동시성 1, service worker 차단, redirect/frame/subresource/XHR/WebSocket/download/popup 전부에 exact-origin 정책과 OS firewall을 함께 적용해야 한다. v1에는 두 도구의 실행 코드나 dependencies가 없다.
