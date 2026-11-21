# 운영자 검사 워크스페이스 검증 — 2026-11-15

운영자가 UI에서 등록 프로필을 선택하고 구체적인 계획을 확인한 뒤 기존 operator-resource-http 실행기를 실행하여 결과·증거·재판정·재현 보고서를 확인하는 흐름을 구현했다. 기존 엔진·verifier·TLS/DNS 연결 정책은 재설계하지 않았다.

## 기준과 변경 구분

- 시작 기준: `8aff74fcbe76a61055bbb8a8f30c1776f0b1599c`, `codex/domain-https-scope`. PR #1–#4 미병합 확인. 새 브랜치 `codex/operator-workspace`, Draft PR base `codex/domain-https-scope`.
- 최종 구현/전체 테스트 커밋: `23cae0f160c4a6e79c7252c179d5084dcad40569`.
- 선행 기능: operator-resource 계약/CLI preview·run, 독립 첨부파일 API, IP HTTPS, 도메인 HTTPS와 DNS/IP 제한.
- 이번 변경: 인증된 Controller workspace API, 서버 전용 프로필 설정, 공유 실행 전 검사 추출, 제출 journal/중복 방지/중단 복구, React workspace, 정제 파생 보고서, UI/API 통합 helper 및 회귀.
- 기존 환경파일·DB·VM·방화벽·registry·hosts/DNS/전역 CA를 수정하지 않았다. 기존 검증 기록을 보존했고 main 병합·실제 VM 배포는 하지 않았다.

## 실제 브라우저 관측

실제 IAB 브라우저 → Controller TCP → Worker function/MCP TCP → 기존 첨부파일 API의 TLS socket을 사용했다. 도메인 답변은 `.test`에 대한 테스트 resolver 주입이다. Target/Worker/Controller와 SQLite, 인증정보, 인증서/키는 모두 임시 테스트 자원이었다. provider는 mock이다.

| 동작 | 실제 관측 |
| --- | --- |
| 준비 상태·첫 preview | Target TCP/TLS/HTTP 모두 0. Worker 정책 조회만 수행 |
| 취약 + cookie + function | `run_5668df00b4a744fabae19bfa388420fe`, VULNERABLE |
| 수정 + cookie + MCP | `run_bbfd081a81e14cc58a70b4c857396e98`, BLOCKED_BY_ACCESS_CONTROL |
| 각 정상 실행 | HTTP 11 / 도구 12 / 증거 11, 저장 증거 재판정 일치 |
| MCP 새 preview | 앞선 11회에서 Target 요청 증가 0 |
| preview 후 Worker revision 변경 | UI에서 새 preview 필요 안내. Target 누적 22 유지, 새 run/제출 없음 |
| 새로고침 | 기존 function plan/run과 완료 결과 복원 |
| 저장된 검사 다시 열기 | MCP 결과·재판정·다운로드 링크 표시 |
| Markdown/JSON 다운로드 | 실제 브라우저 다운로드 파일 파싱. evidence ID 11개와 placeholder, 판정/재판정 일치 확인 |
| 긴 상세 | HTTP 11개와 연결 관측 11개를 펼쳐도 실행 버튼 하단 유지(top 715/bottom 769, viewport 높이 794) |
| 기존 UI | 기존 시나리오·채팅 이동 및 workspace 복귀 확인. 기존 시나리오를 브라우저에서 추가 실행하지 않음 |

`browser/execution.json`에 시점별 Target 수신/연결 계수와 제출/정책/CA fingerprint가 있다. `browser_checks.json`은 실제 UI 동작과 다운로드 SHA-256을 기록한다. `browser/run_*/`는 원래 증거에서 만든 공개 결과/파생 보고서다. screenshot은 `browser-result.jpg`다. 기존 네트워크 전체 행렬을 수동 반복한 결과가 아니다.

브라우저는 기준 8aff74f 위의 **미커밋 구현 상태**에서 실행했다. `working_tree_dirty=true`와 원래 소스 해시를 그대로 보존했다. 브라우저 실행을 최종 clean commit에서 수행했다고 주장하지 않는다. `browser_source_audit.json`은 실행 소스와 최종 LF 정규화 소스를 연결한다. 비교한 6개 파일 중 5개는 정규화 전 동일하고, `workspace_api.py`는 사용하지 않은 import 제거만 달라졌다. 이후 테스트 helper의 임시 DB 정리와 좁은 화면의 CSS wrapping을 수정했다. 최종 CSS는 빌드 검증이며 그 수정 후 두 번째 브라우저 E2E를 실행하지 않았다.

## API/회귀 검증의 의미

새 테스트는 실제 Controller/Worker TCP 및 Target TLS로 다음을 검사한다.

- 인증 없음/잘못된 세션, CSRF/Origin/Host 위반, URL·CA·계정·IP 범위·한도·provider override 거절. 기존 client allowlist middleware도 모든 새 API에 적용한다.
- 변조·만료·사용된 계획 및 불일치 digest/미확인 실행 거절.
- 같은 plan에 동시 요청 6건: 202 한 건, 409 다섯 건, Target HTTP 11, claimed 이력 한 건. 이후 다시 제출해도 추가 요청 없음.
- POST 응답 본문을 버린 뒤 알려진 plan ID로 run 상태 복구. **회선 단절을 일으킨 시험은 아니며 응답 유실 의미를 시뮬레이션**했다.
- Worker 정책 변경은 claim과 첫 Target 요청 전 거절. 서버 프로필을 동기화한 새 preview는 다른 digest를 발급.
- 잘못된 ID/path와 고정 다운로드 형식 외 입력 거절. symlink 거절은 Windows 생성 권한에 의존하지 않는 주입 회귀이며 실제 junction 파일 시스템 공격 시험은 아님.
- Controller 재시작을 모사한 journal 재개: 미완료 receipt는 INTERRUPTED, task 재생성 없음, 동일 계획 재제출 거절.
- 구형 CLI operator 보고서 조회/다운로드 및 원본 모든 파일의 바이트 불변 확인.
- 각 정상 flow의 11/12/11, 재판정 일치와 공개 결과에 생성 비밀값 미포함 확인.
- 임시 Controller 종료 후 테스트 DB 디렉터리 삭제 가능 회귀.

`api_cleanup_validation/`은 helper 수정 후 반복 가능한 CLI helper를 실행한 실제 결과다. function/MCP 두 flow와 정제 산출물 생성, listener 종료, 임시 runtime 삭제가 완료됐다. 기존 fixture를 복제하지 않았다.

## 발견한 오류와 처리

1. 초기 신규 테스트에서 이미 열린 httpx Client를 다시 context manager로 열어 2건 실패했다. 제품 실행 경로 실패가 아닌 테스트 helper 오용이었으며 `contextlib.closing`으로 수정했다.
2. 첫 브라우저 helper는 공개 결과 내보내기 후 Windows 임시 SQLite 파일 정리에 실패했다. 기존 Repository의 sqlite3 transaction context가 연결을 직접 닫지 않아 수집 전 cycle이 남은 원인이었다. 프로세스 종료 후 **해당 임시 디렉터리만** 정리했다. 테스트 Controller가 멈춘 뒤 unreachable connection을 수집하도록 test helper를 수정했고 제거 회귀와 후속 helper 실행이 통과했다. 기존 DB 또는 Repository 스키마는 변경하지 않았다.
3. 브라우저 자동화의 exact-text/role locator 두 건이 공백 및 native details 역할 차이로 일치하지 않았다. 실제 UI 상태를 읽어 컨트롤을 다시 지정했고 실행 판정이나 기대값을 바꾸지 않았다.
4. 좁은 기본 브라우저 화면에서 긴 식별자에 대한 가로 스크롤을 관측하여 grid min-width/wrapping을 보완했다. 후속 build는 통과했으며 수정 후 브라우저 재검증은 미수행으로 구분한다.

최종 전체 pytest는 **920 passed, 41 warnings, 314.77초, exit 0**이다. 경고는 기존 Pydantic/MCP deprecated helper 및 pytest cache 쓰기 권한에 관한 것이다. frontend 테스트 **16 passed**, build **21 modules / 298ms / exit 0**이다. 실행 명령은 `verification_summary.json`에 기록했다. 최종 전체 통과 후 실행 코드 변경이나 동일 전체 테스트 재실행은 하지 않았다.

## 공개·보존 검사

브라우저 public 산출물은 생성 비밀값/키/경로 23개, 후속 API helper public 산출물도 23개와 대조하여 일치 0이었다(각 실행별 검사이며 고유 값 46개라고 단정하지 않음). 공개된 것은 alias/resource ID, evidence ID, proof의 commitment/run digest, scope/CA hash, 허용 origin/IP, 정제 reason 및 사용량이다. 비밀번호·cookie·Bearer·raw proof·개인키·원본 응답·민감한 로컬 경로는 공개하지 않는다.

브라우저 원래 cleanup 실패 기록은 `browser/cleanup_recovery.json`, 수정 후 자동 정리는 `api_cleanup_validation/cleanup.json`에서 분리 확인한다. 원본 report/evidence를 수정하지 않고 파생 보고서만 생성했다. 최종 source/artifact manifest는 Git byte 보존 규칙과 함께 기록한다.

## 지원 범위와 미검증 범위

단일 운영자, 단일 Controller process, 서버에 준비한 프로필, mock와 고정 read flow가 범위다. 브라우저를 닫아도 작업은 Controller에서 계속되지만 **Controller 프로세스 장애를 넘어 자동 실행 재개하지 않는다**. 이 경우 중단 이력과 부분 증거를 검토하고 새 계획이 필요하다. 다중 process journal 소유권/분산 queue/RBAC는 지원하지 않는다.

이 UI 검증은 cookie + function 취약 / MCP 수정 두 대표 조합이다. Bearer·모든 TLS/DNS 실패의 전체 브라우저 행렬은 반복하지 않았다. 기존 HTTP/IP HTTPS/domain HTTPS 및 documents/records 회귀는 전체 pytest로 확인한다. OS 실제 DNS/외부 서비스/VM/실전 버그 바운티/새 취약점/유료 모델은 검증 범위 밖이다. 테스트 브라우저 제어를 대상 탐색 도구로 추가한 것이 아니다.

다음 작업은 이 Draft PR의 사용자 흐름·권한 경계·증거 검토다. main 병합이나 실제 VM 배포는 별도 승인 범위이며 이번 작업에서 수행하지 않는다.
