# operator-resource-http 실제 VM 검증 — 2026-11-07

Controller·Worker·Target 세 Ubuntu VM에서 **새 preview → 실제 계획 검토 → digest를 명시한 별도 run**을 네 번 실행했다. 취약/function·MCP는 `VULNERABLE`, 수정/function·MCP는 `BLOCKED_BY_ACCESS_CONTROL`이다. 모든 preview의 Target HTTP 요청 증가는 0, run의 실제 API 수신은 11, Worker 사용량은 HTTP 11/도구 12, 저장 증거는 11개다. 네 실행 모두 정책 연결과 저장 증거 재판정이 일치했다. 기존 서비스 복구와 보존 검사까지 완료했다.

기준 커밋은 `b574ba4179c8413ca61a181fa6c987898faf555f`, VM에서 실행한 커밋은 launcher를 추가한 `aa6143245c19cb917b26e056684c498358570cba`다. Controller/Worker의 operator-resource 계약·preview/run·verifier 구현은 기준 커밋 그대로다. 작업 브랜치는 `codex/operator-resource-vm-verification`이며 main에 병합하지 않았다.

## 실제 결과

실행 시각은 Controller 기준 2026-11-07 07:02:24–07:05:20 UTC, 한국 시각 16:02:24–16:05:20이다. VM 사이 시계에는 작은 차이가 있어 서로 다른 VM의 timestamp만으로 순서를 비교하지 않았다. 호스트에서 이전 작업 완료를 확인하며 요청 계수/preview/검토/run 단계를 전달했다. 취약 MCP의 마지막 계수는 HTTP 11회가 완료된 뒤 최종 보고서 직렬화와 가까운 시점에 수집됐다.

| 조합 | 판정 | preview 전/후/run 후 수신 계수 | preview 요청 | run HTTP / 도구 / 증거 | 정책·재판정 |
|---|---|---|---:|---|---|
| [취약/function](vulnerable-function/plan.md) | VULNERABLE | 1 / 1 / 12 | 0 | 11 / 12 / 11 | 일치 |
| [취약/MCP](vulnerable-mcp/plan.md) | VULNERABLE | 12 / 12 / 23 | 0 | 11 / 12 / 11 | 일치 |
| [수정/function](fixed-function/plan.md) | BLOCKED_BY_ACCESS_CONTROL | 1 / 1 / 12 | 0 | 11 / 12 / 11 | 일치 |
| [수정/MCP](fixed-mcp/plan.md) | BLOCKED_BY_ACCESS_CONTROL | 12 / 12 / 23 | 0 | 11 / 12 / 11 | 일치 |

취약 판정의 reason은 `CROSS_ACCOUNT_PRIVATE_PROOF`, 수정 판정은 `EXPLICIT_DENIAL_WITH_STABLE_CONTROLS`다. [기계 판독 요약](summary.json)에 실제 run ID/plan ID/digest가 있고, 각 조합 폴더에 catalogue, plan, 검토 기록, issued/claimed 이력, candidate_execution 연결, evidence, verification_contract, report, replay가 있다. 이들은 VM이 기록한 byte를 유지했다.

Target의 최초 계수 1은 시작 후 health다. 구간 안에서는 다른 health 요청을 보내지 않았다. 같은 Target PID/시작 시각의 전후 계수를 비교했으며 fixed 전환 때만 카운터가 새 프로세스에서 시작됐다. 계수는 API 미들웨어의 **실제 수신 요청 수**이며 TCP 패킷 수/패킷 캡처가 아니다. 계수 파일은 verifier 입력이 아니다. 수정/MCP 마지막 계수 수집은 Windows 공유 파일 rename 잠금으로 한 번 실패했다. Target 정상 종료 후 남은 같은 PID의 최종 파일에서 23을 회수했다. 복구된 기존 Target은 이 파일을 쓰지 않는다.

## 실행 경계와 정책 연결

Controller의 별도 checkout에서 `controller.candidates import-openapi`와 `controller.operator_execution preview/run`을 실행했다. `controller.cli`의 기존 시나리오 실행으로 대체하지 않았다. function과 Streamable HTTP MCP는 실제 `10.77.0.20:9000` Worker에 연결했고, Worker는 실제 `10.78.0.30:8080` 독립 API에 TCP 요청을 보냈다. 기존 Controller API/UI는 검증 경로로 사용하지 않았다. provider는 `mock`, 인증은 cookie다.

API는 새 in-memory 데이터로 `/session`, `/me`, 등록된 두 `/tickets/{resource_id}`와 health만 제공한다. 두 계정 비밀번호와 두 proof는 새 고엔트로피 값으로 만들었다. 별도 Target/Worker 환경파일만 값을 보유하며 Controller에는 proof commitment와 run digest만 전달한다. 기존 target DB, TargetStore, canary helper, target 로그/모드/fixture 정답을 verifier에 주지 않았다. 운영 harness의 기대 결과 비교에만 모드 라벨을 사용했다.

계획마다 cookie 인증, 등록된 두 리소스, login 2회 → identity 2회 → 소유자 resource 2회 → 교차 resource 1회 → 소유자 재조회 2회 → identity 재조회 2회의 11단계를 읽고 검토했다. 각 계획은 새로운 ID, 300초 만료, `NOT_EXECUTED` 상태로 발급됐고 검토 후 별도 명령에 literal SHA-256을 넣었다. `approval_actor=codex`, `approval_identity_authenticated=false`이며 인간 인증 서명으로 주장하지 않는다.

실제 Worker policy는 `operator-prepared-resources`, revision 1, snapshot `4022028635b5dac5918814f2848892e04037c856577f3ad5cd31722130324922`다. 한도는 HTTP 11, 도구 12, 요청 timeout 5초, run timeout 180초, 응답 65536 byte, 초당 2회, 동시 실행 1이다. source/registry hash, plan digest, issued/claimed, expected/actual scope policy, report policy의 연결을 비교했다. 각 실행의 정책 조회는 preview 1회/run 1회이며 도구 12회나 Target HTTP 11회에 포함되지 않는다. snapshot은 정책 식별 정보이고 서명이 아니다.

Guest Controller에서 저장 evidence/contract/report만으로 재판정했고, 공개 폴더로 회수한 byte를 호스트에서 재판정해 다시 일치함을 확인했다. 새 Controller checkout에는 issued/claimed 8개와 run report 4개가 남아 있다.

## 기존 서비스와 데이터 복구

기존 checkout은 `/home/ubuntu/securityaiagent`, 테스트 checkout은 `/home/ubuntu/securityaiagent-operator-vm-20261106`이다. 코드 Git bundle, 코드·환경 archive, SQLite online backup과 비교 기준은 각 VM의 `/home/ubuntu/securityaiagent-operator-vm-state-20261106/private`에 보관했다. 비밀 파일은 0600, private 디렉터리는 0700이다. 기존 venv를 참조했으며 의존성을 설치하거나 기존 환경파일/DB를 수정하지 않았다.

| VM | 이번 보존 검사 기준 HEAD | 기존 실행 방식 | 복구 health | DB 검사 |
|---|---|---|---:|---|
| Controller | e54d776, 11월 7일 재백업 | 기존 uvicorn factory + `.env.controller`, 8000 | 200 | 2개, 모든 행 동일 |
| Worker | ef25892, 11월 6일 백업·7일 재확인 | common.service_config serve worker + `.env.worker`, 9000 | 200 | 1개, 모든 행 동일 |
| Target | ef25892, 11월 6일 백업·7일 재확인 | common.service_config serve target + `.env.target`, 8080 | 200 | 5개, 모든 행 동일 |

재개 시 세 서비스가 정지 상태였으므로 기존 설정으로 먼저 기동하고 health를 확인했다. Worker/Target은 listener의 cwd/module을 확인한 뒤 같은 포트의 기존 프로세스만 SIGTERM으로 종료했다. 테스트 종료 후 새 Worker/Target도 SIGTERM으로 정상 종료하고 기존 서비스를 복구했다. Controller 기존 서비스는 계속 유지했다. Controller health는 기존 client allowlist가 허용하는 loopback source로 기존 주소의 `/api/health`를 조회했다.

[Controller](controller/controller-final.json), [Worker](worker/worker-final.json), [Target](target/target-final.json) 최종 기록에서 코드 HEAD, 환경/config/기존 report·plan 파일 해시, SQLite quick_check와 전체 행 동일성을 확인할 수 있다. guest NIC/MAC/IP 및 정규화한 iptables 규칙 hash도 같다. 호스트의 VirtualBox NIC/MAC/network 설정과 원래 공유 mapping을 전후 비교했다. 이번에 추가한 transient 공유는 세 VM에서 마운트 해제한 뒤 제거했고 전달기는 종료했다. 기존 `securityai-update` 공유는 유지했다. 테스트 checkout·새 환경·백업·계획·증거는 보존했다.

**Controller 보존 범위는 11월 7일 재개 시점부터다.** 전날 기록은 ef25892였지만 재개 시 e54d776/codex/compact-chat-layout이었고 전날 작업용 디렉터리가 없었다. 변경 원인은 확인하지 못했다. 현재 상태를 먼저 백업했으며, 전날 Controller 상태까지 보존됐다고 주장하지 않는다.

## 장애와 해결

| 발생 단계 | 실제 실패/관찰 | 처리 및 결과 |
|---|---|---|
| 11월 6일 Controller 부팅 | 콘솔·정상 종료 무응답, live snapshot 90% 정체 | 완료 백업으로 간주하지 않았다. 사용자 승인 후 해당 VM만 강제 종료·재기동했다. 이후 별도 코드/DB 백업과 integrity 검사를 수행했다. |
| VM 전달 | 로그인/자동 잠금, 터미널 입력 일부 누락 | 사용자 로그인·sudo 이후 고정 action dispatcher로 전달했다. 앱 run 실패로 계산하지 않았다. |
| 11월 7일 Controller 재개 | 작업용 private 디렉터리 없음으로 dispatcher FileNotFoundError; 이전 가정의 service_config 모듈 없음 | 실제 HEAD e54d776과 기존 uvicorn 실행 방법을 확인하고 재백업/별도 checkout을 만들었다. 기존 코드나 설정을 업그레이드하지 않았다. |
| 기존 Controller health 관찰 | 자기 외부 IP를 source로 조회할 때 HTTP 오류 | 기존 allowlist를 바꾸지 않고 허용된 loopback source에서 health 200을 확인했다. |
| 호스트 직접 health 시도 | sandbox WinError 10013 | 네트워크 샌드박스 오류로 구분했다. 최종 서비스 health는 각 VM에서 확인했다. |
| 공유 job 파일 전달 | Target 마지막 counter 및 Worker restore 전달에서 WinError 5 rename 실패 | Windows 공유 파일 열림 경합에 짧은 재시도를 추가했다. 명령 전달 전 실패였으며 미실행 명령만 다시 보냈다. 복구/계수 회수 완료. |
| 초기 로컬 focused 검증 | 42개 중 2개 실패: 새 역할의 표준 `.env.operator-target.example` 파일이 없었음 | 예제를 표준 위치로 수정 후 전체 717개 통과, frontend build 통과. |

네 실제 VM preview/run에는 실패·INCONCLUSIVE·예상과 다른 판정이 없었다. 최초 전송 manifest의 helper hash는 health/legacy launcher 수정 이전 값이므로 최종 helper 검증값으로 쓰지 않는다. [최종 hash 목록](SHA256SUMS.json)과 [사용한 운영 helper](operational_helpers/)를 별도로 보존한다. helper는 한 번의 VM 작업을 위한 제한된 action 도구이며 일반 배포 인터페이스가 아니다.

## 로컬 검증과 미검증 범위

launcher 추가 후 로컬 전체 pytest는 **717 passed, 12 warnings, 280.37초**, `npm run build`는 성공했다. 이는 준비 단계 회귀 검증이다. 위 VM 결과는 별도의 네 실제 네트워크 실행으로 얻었으며 기존 로컬 706개 테스트의 반복을 VM 검증으로 대체하지 않았다. 회수 후 네 저장 증거의 오프라인 재판정을 추가 수행했다.

이번 VM 검증은 cookie·mock·등록된 두 리소스의 고정 read flow에 한정된다. Bearer의 VM 동작, UI/브라우저, Nmap, Playwright, live OpenAI, 임의 사이트/리소스, 장애 주입 및 정책 변경 거절 테스트는 이번 VM에서 실행하지 않았다. 기존 controller SQLite에 새 테스트 run을 넣지 않았으며 새 파일 기반 plan/run 이력을 별도 checkout에 보존했다.

공개 산출물에는 환경파일, 원본 DB, 원본 Target 로그, 비밀번호, raw proof, session cookie, 응답 본문을 포함하지 않았다. 새 환경의 비밀값과 공개 파일을 대조해 일치가 없음을 검사했다. [공개 검사 결과](publication_checks.json)를 함께 기록한다.
