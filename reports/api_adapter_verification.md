# API 어댑터 로컬 검증 — 2026-10-27

`codex/service-auth-config`의 `ac1e00f`를 기반으로 만든 `codex/target-api-adapters` 작업이다. Codex가 로컬 Windows에서 실제 loopback TCP target/worker 서버를 실행해 JSON 증거를 생성·검사했다. 사용자 제공 VM UI 출력이나 VM 원본 파일 직접 검사와 구분한다. 이전 mock/OpenAI 결과와 422 실패·git bundle·TARGET_MODE 재시작 이력은 기존 문서에 그대로 남겼다.

실행 명령: `.\.venv\Scripts\python.exe -m scripts.run_adapter_verification`. 모든 실행은 `provider=mock`, `scenario=access-control-http`, `verification_basis=http_observation`이다. target fixture 모드는 테스트 harness만 알고 verifier에는 전달하지 않았다. target DB/log reader를 호출하면 실패하도록 설정했다. target middleware가 독립적으로 센 요청 수와 worker가 반환한 실제 `limits_used.http_requests`가 16건 모두 일치했다. UI 정책 상한을 사용량으로 기록하지 않았다.

원본 행렬: [matrix-f36d4e7ff64b.json](api_adapters/matrix-f36d4e7ff64b.json). 각 run 디렉터리에 정제된 report.json, evidence.json, report.md를 저장했다. snapshot hash에는 테스트마다 예약한 loopback origin이 포함되므로 VM hash 또는 다른 재실행 hash와 같아야 하는 값이 아니다. 기본 프로필은 r4, records는 r1이며 기존 VM r1 결과를 대체하지 않는다.

## 실제 TCP 정상 8조합

모두 COMPLETED, 증거 7개, HTTP 9회, 도구 10회. 저장된 증거만으로 재판정한 verdict도 모두 보고서와 일치했다.

| API | Mode | Transport | Verdict | Run / evidence |
|---|---|---|---|---|
| documents | vulnerable | function | VULNERABLE | [adapter-dbb69f591df24a2aa4db3349a5946e0b](api_adapters/adapter-dbb69f591df24a2aa4db3349a5946e0b/report.json) / [evidence](api_adapters/adapter-dbb69f591df24a2aa4db3349a5946e0b/evidence.json) |
| documents | vulnerable | mcp | VULNERABLE | [adapter-3d1619115fcb49568cf6d41c48f1ce89](api_adapters/adapter-3d1619115fcb49568cf6d41c48f1ce89/report.json) / [evidence](api_adapters/adapter-3d1619115fcb49568cf6d41c48f1ce89/evidence.json) |
| documents | fixed | function | BLOCKED_BY_ACCESS_CONTROL | [adapter-bd9aaf3694864f22b78b37dc8155d315](api_adapters/adapter-bd9aaf3694864f22b78b37dc8155d315/report.json) / [evidence](api_adapters/adapter-bd9aaf3694864f22b78b37dc8155d315/evidence.json) |
| documents | fixed | mcp | BLOCKED_BY_ACCESS_CONTROL | [adapter-445b7810697f4879a2191c050af36beb](api_adapters/adapter-445b7810697f4879a2191c050af36beb/report.json) / [evidence](api_adapters/adapter-445b7810697f4879a2191c050af36beb/evidence.json) |
| records | vulnerable | function | VULNERABLE | [adapter-898fbe4261ce4ed9b843f6fc8dae776a](api_adapters/adapter-898fbe4261ce4ed9b843f6fc8dae776a/report.json) / [evidence](api_adapters/adapter-898fbe4261ce4ed9b843f6fc8dae776a/evidence.json) |
| records | vulnerable | mcp | VULNERABLE | [adapter-d316b2d5378d4ba29ec0bed69a7011f4](api_adapters/adapter-d316b2d5378d4ba29ec0bed69a7011f4/report.json) / [evidence](api_adapters/adapter-d316b2d5378d4ba29ec0bed69a7011f4/evidence.json) |
| records | fixed | function | BLOCKED_BY_ACCESS_CONTROL | [adapter-702d80ede46641cb8442e971a46c69aa](api_adapters/adapter-702d80ede46641cb8442e971a46c69aa/report.json) / [evidence](api_adapters/adapter-702d80ede46641cb8442e971a46c69aa/evidence.json) |
| records | fixed | mcp | BLOCKED_BY_ACCESS_CONTROL | [adapter-3da2d5e3de6e4b6aa06e6395eb7403f0](api_adapters/adapter-3da2d5e3de6e4b6aa06e6395eb7403f0/report.json) / [evidence](api_adapters/adapter-3da2d5e3de6e4b6aa06e6395eb7403f0/evidence.json) |

## 실제 TCP 거절 8건

두 API 각각 function/MCP로 계정 거절과 요청 한도 차단을 확인했다. 모두 INCONCLUSIVE, 증거 0개다. 계정 시험은 user-a만 승인하여 첫 로그인 이후 user-b를 거절했다. 한도 시험은 HTTP 2회까지만 허용했다. 정상 모드 8조합 외에 취약 fixture에서 수행한 음성 대조군이다.

| API | Case | Transport | Actual HTTP / tools | Rejection | Run / evidence |
|---|---|---|---|---|---|
| documents | account-denied | function | 1 / 1 | SCOPE_ACCOUNT_DENIED | [adapter-658ba5a7f47f451e938ecc1144f21b5d](api_adapters/adapter-658ba5a7f47f451e938ecc1144f21b5d/report.json) / [evidence](api_adapters/adapter-658ba5a7f47f451e938ecc1144f21b5d/evidence.json) |
| documents | account-denied | mcp | 1 / 1 | SCOPE_ACCOUNT_DENIED | [adapter-c2306f19ed73451fad3b36cdfa56f1f5](api_adapters/adapter-c2306f19ed73451fad3b36cdfa56f1f5/report.json) / [evidence](api_adapters/adapter-c2306f19ed73451fad3b36cdfa56f1f5/evidence.json) |
| documents | limit-two | function | 2 / 3 | SCOPE_LIMIT_EXCEEDED | [adapter-b88031fd865c48c3b450d7d15d634be8](api_adapters/adapter-b88031fd865c48c3b450d7d15d634be8/report.json) / [evidence](api_adapters/adapter-b88031fd865c48c3b450d7d15d634be8/evidence.json) |
| documents | limit-two | mcp | 2 / 3 | SCOPE_LIMIT_EXCEEDED | [adapter-bd71682d64b044e7ad9ed303abea5e23](api_adapters/adapter-bd71682d64b044e7ad9ed303abea5e23/report.json) / [evidence](api_adapters/adapter-bd71682d64b044e7ad9ed303abea5e23/evidence.json) |
| records | account-denied | function | 1 / 1 | SCOPE_ACCOUNT_DENIED | [adapter-102afa5d76ff4fbea7482864fed91eec](api_adapters/adapter-102afa5d76ff4fbea7482864fed91eec/report.json) / [evidence](api_adapters/adapter-102afa5d76ff4fbea7482864fed91eec/evidence.json) |
| records | account-denied | mcp | 1 / 1 | SCOPE_ACCOUNT_DENIED | [adapter-b3f5644242d84d8e8294ae9736cad1c8](api_adapters/adapter-b3f5644242d84d8e8294ae9736cad1c8/report.json) / [evidence](api_adapters/adapter-b3f5644242d84d8e8294ae9736cad1c8/evidence.json) |
| records | limit-two | function | 2 / 3 | SCOPE_LIMIT_EXCEEDED | [adapter-16b2e14f3f9c4eb09cd8036b655cb896](api_adapters/adapter-16b2e14f3f9c4eb09cd8036b655cb896/report.json) / [evidence](api_adapters/adapter-16b2e14f3f9c4eb09cd8036b655cb896/evidence.json) |
| records | limit-two | mcp | 2 / 3 | SCOPE_LIMIT_EXCEEDED | [adapter-c4c6360b0b8745aca6b2be22d376182b](api_adapters/adapter-c4c6360b0b8745aca6b2be22d376182b/report.json) / [evidence](api_adapters/adapter-c4c6360b0b8745aca6b2be22d376182b/evidence.json) |

## 회귀 범위

- `tests/test_api_adapters.py`: 두 API의 공개 본인/공개 교차 리소스, 없는 ID, 로그인 실패, 잘못된 목록/상세, JSON 중복 키, 일반 오류를 위장한 거절, HTML 로그인, 응답 계정 식별 누락을 INCONCLUSIVE로 확인했다. ASGI 응답 변형 시험이며 실제 TCP 오류 서버 또는 VM 오류 재현은 아니다.
- 계정 첫 요청부터 거절(0 HTTP), 2회 한도, 최종 전송의 잘못된 method/path/origin 차단을 두 API에서 검증했다. 어댑터만으로 Scope 경로 확대 불가, 실행 도중 registry 파일 변경에도 snapshot 유지, 응답 필드 매핑 변경의 fingerprint 반영을 확인했다.
- strict 스키마의 unknown/위험 필드·경로 거절, 환경변수 비밀 참조 누락/평문 비밀번호 금지, 보고서·engine 이벤트에 비밀번호와 원문 쿠키·Bearer 토큰·합성 내용이 없음을 검사했다.
- 기존 service 환경 분리, Scope, HTTP 검증기와 legacy 로그 기반 시나리오 회귀를 함께 실행했다.

Python 전체 회귀: **332 passed, 7 warnings, 200.12초**. 기존 MCP/Pydantic 의존성 경고 7건이며 실패는 없었다.

프런트엔드 `npm test`: **14 passed**. `npm run build`: **성공**. 브라우저 E2E 실행을 의미하지 않는다.

## 사용자 제공 VM 정상 8조합 — 2026-10-30 기록

출처: **사용자 제공 VM UI 및 Controller 재판정 출력**. 아래는 사용자가 실제 VM에서 실행하고 Controller의 저장된 증거로 재판정했다고 제공한 결과다. Codex는 VM 원본 파일을 확보하거나 직접 검사하지 않았으며 VM 재실행도 하지 않았다. 기록일은 실행 시각을 의미하지 않는다.

모두 `mock` / `access-control-http`, `COMPLETED`, `evidence_count=7`, `verdict_matches=true`다. 각 실행의 **실제 사용량**은 HTTP 요청 9회·도구 호출 10회이며 정책 상한 표시를 사용량으로 옮긴 것이 아니다. 설정 모드는 사용자 작업 이력이며 HTTP Verifier 입력이 아니다. 정책 hash, VM별 commit, 실행 시각, 환경 버전은 미제공이다. 원본 증거 파일 링크는 만들지 않았다.

| API / revision | 사용자 설정 모드 | 연결 | run_id | 판정 |
|---|---|---|---|---|
| documents r4 | fixed | function | `run_c91a9ac2317d49e18dd0545b325ce6f9` | BLOCKED_BY_ACCESS_CONTROL |
| documents r4 | fixed | mcp | `run_3b997adb0d194bdd97b9a32e97169346` | BLOCKED_BY_ACCESS_CONTROL |
| documents r4 | vulnerable | function | `run_d6635b330ff348dfa0e10c7f5fbf0a1e` | VULNERABLE |
| documents r4 | vulnerable | mcp | `run_67f60df099684b2582dce2ac80f03b4e` | VULNERABLE |
| records r1 | fixed | function | `run_7139b4e0c56947a290048efa451b1079` | BLOCKED_BY_ACCESS_CONTROL |
| records r1 | fixed | mcp | `run_8f7031d015384cf38e243f04a24af07c` | BLOCKED_BY_ACCESS_CONTROL |
| records r1 | vulnerable | function | `run_64945b71f35a4da9b7411462183d02a1` | VULNERABLE |
| records r1 | vulnerable | mcp | `run_897c1f09f83446fe965bcc7a2800c421` | VULNERABLE |

VM 정상 8조합은 위 사용자 제공 출력 범위에서 확인됐으며, 앞의 Codex 직접 실행 로컬 TCP 16건과 별도 증거다. 이번 갱신은 문서만 변경했으며 테스트와 OpenAI 호출을 재실행하지 않았다. 이전 OpenAI 결과와 실패 이력도 유지한다.

## 미검증 범위

새 어댑터의 **계정 거절·한도 차단 VM 검증**, VM 원본 파일 직접 검사, VM NIC/방화벽, 사용자 브라우저 E2E, 새 어댑터의 OpenAI 실호출·비용·모델 품질, 외부 사이트 적용은 미검증이다. 이번 작업은 OpenAI API를 호출하지 않았다. 기존 사용자 제공 gpt-5.4-mini 네 실행은 기존 API의 역사적 증거이며 새 records 어댑터 검증으로 재사용하지 않는다. Nmap/Playwright는 phase 2로 미구현이다.

지원 범위는 등록된 로컬 합성 대상과 정해진 ID/계정/읽기 동작이다. OAuth, refresh token, MFA, HTML 폼 로그인, CSRF 흐름, pagination, 임의 API schema 또는 임의 웹사이트를 지원한다고 주장하지 않는다. 운영자 설정·VM별 명령은 [target_api_adapters.md](../docs/target_api_adapters.md)에 있다.
