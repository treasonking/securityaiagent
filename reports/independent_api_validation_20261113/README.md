# 독립 프로젝트 첨부파일 API — 실제 로컬 TCP 검증

**기존 엔진·계약·verifier를 변경하지 않고, 경로·로그인 이름·중첩 응답·리소스 ID가 다른 API를 전용 registry/어댑터 설정으로 연결했다.** 정상 8조합과 실패 조건 8건은 모두 사전에 정한 기준을 충족했다. 이는 구조를 알고 설정한 단일 API의 내부 적용성 검증이며 블라인드 평가나 외부 사이트 일반화 성능은 아니다.

시작 기준은 `4f637f58142b967aca0986d2ffc83b537ce9c4db`다. PR #1은 시작 시 미병합, 원격 main은 `17d72b8`이었다. 실제 행렬 실행 코드는 **`ef505eff010b0ed96d83057a2a0cf3dfb680242c`**, 실행 시작 시 작업 트리는 clean이었다. 2026-11-13 **16:11:36 KST (07:11:36 UTC)**부터 25.063초 동안 실행했다. 이후 문서·증거와 입력 JSON의 검증 당시 개행 보존을 추가했으며 실행 로직은 동일하다. [matrix.json](matrix.json)에 실행 커밋, 도구/대상/기존 엔진의 source SHA-256, 개별 plan/run 연결과 측정값이 있다.

최종 stage 감사에서 전용 입력 JSON 3개의 working-tree CRLF가 최초 Git blob에서는 LF로 정규화됐음을 발견했다. 구조·값의 차이는 없지만 원본 byte digest는 달랐다. `.gitattributes`로 해당 입력을 `-text` 보존하고 **실제로 검증한 CRLF byte**를 최종 커밋에 기록했다. 실행/plan hash를 다시 계산해 결과를 맞추지 않았다. 따라서 최초 코드 커밋만 다른 OS에서 checkout한 byte와 비교할 때에는 이 개행 차이를 구분하며, 최종 브랜치 입력과 matrix source hash는 일치한다.

## 실제 정상 행렬

모든 행에서 preview 대상 요청 **0**, 실제 API 수신 **11**, Worker **HTTP 11 / tools 12**, evidence **11**, plan/snapshot/run 연결 및 저장 증거 재판정 일치다. function은 Worker REST로 실제 TCP 요청을 보냈고, MCP는 실제 Streamable HTTP 세션과 tool call을 사용했다.

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

수정 모드의 두 소유자 조회와 재조회는 200, 교차 조회는 403이다. 취약 모드의 교차 조회는 200과 등록된 다른 소유자의 비공개 proof 관찰로 판정했다. 서버 모드·프로젝트 저장 모델·계수·기대 verdict는 verifier 입력이 아니다.

각 정상 function 행의 Worker 수신 계수는 정책 조회 2, function endpoint 12다. 각 정상 MCP 행은 정책 조회 2, `/mcp` 요청 15다. 15는 handshake/제어를 포함한 HTTP 수신 횟수로 **tool 12회와 다른 측정값**이다. 실제 Target API의 handler 계수 11과 분리했다. 소켓 패킷 캡처나 함수 직접 호출을 TCP 측정으로 표시하지 않았다.

## 실패 조건별 실제 경계

모든 실패 조건은 cookie 인증이며 function/MCP를 각각 실행했다. 기대 결과는 변경하지 않았다.

| 조건 | 전송 | Target / 도구 / 증거 | 실제 상태·reason | 차단 시점 |
|---|---|---|---|---|
| preview 후 정책 변경 | [function](cookie-vulnerable-function-policy_change/result.json) | 0 / 미생성 / 0 | REJECTED_BEFORE_RUN, WORKER_POLICY_CHANGED | 새 Worker 정책 재조회, 첫 로그인·claim 전 |
| preview 후 정책 변경 | [MCP](cookie-vulnerable-mcp-policy_change/result.json) | 0 / 미생성 / 0 | REJECTED_BEFORE_RUN, WORKER_POLICY_CHANGED | 새 Worker 정책 재조회, MCP 검사 세션 생성 전 |
| 예산 2 | [function](cookie-vulnerable-function-budget2/result.json) | 2 / 3 / 2 | FAILED, INCONCLUSIVE, SCOPE_LIMIT_EXCEEDED | 세 번째 도구 호출에서 세 번째 HTTP 전송 전 |
| 예산 2 | [MCP](cookie-vulnerable-mcp-budget2/result.json) | 2 / 3 / 2 | FAILED, INCONCLUSIVE, SCOPE_LIMIT_EXCEEDED | 동일 |
| 소유자 불일치 | [function](cookie-vulnerable-function-owner_mismatch/result.json) | 11 / 12 / 11 | COMPLETED, INCONCLUSIVE, OWNER_RESOURCE_PROOF_UNPROVEN | 최초 소유자 조회부터 불일치; 11개 관찰 후 verifier 대조 거절 |
| 소유자 불일치 | [MCP](cookie-vulnerable-mcp-owner_mismatch/result.json) | 11 / 12 / 11 | COMPLETED, INCONCLUSIVE, OWNER_RESOURCE_PROOF_UNPROVEN | 동일 |
| 소유자 재조회 proof 변경 | [function](cookie-vulnerable-function-proof_rotation/result.json) | 11 / 12 / 11 | COMPLETED, INCONCLUSIVE, OWNER_RESOURCE_PROOF_UNPROVEN | 8·9번째 HTTP에서 proof 변경; verifier 대조 거절 |
| 소유자 재조회 proof 변경 | [MCP](cookie-vulnerable-mcp-proof_rotation/result.json) | 11 / 12 / 11 | COMPLETED, INCONCLUSIVE, OWNER_RESOURCE_PROOF_UNPROVEN | 동일 |

정책 변경은 mock 응답 치환이 아니다. preview를 받은 실제 Worker를 종료하고, 별도 proof commitment를 바인딩한 새 Worker를 같은 자체 확보 port에 기동했다. 기존 Controller registry/plan은 유지했다. 두 행의 변경 전후 snapshot은 다르며 실제 정책 HTTP 조회는 각각 2회다. target 요청은 0이고 run/claimed/report가 없으므로 `actual_verdict`, `run_id`, `worker_usage`, `replay`는 null이다. verifier가 INCONCLUSIVE를 반환한 경우와 구분한다. 이 두 행에서는 MCP 도구가 실행됐다고 주장하지 않는다.

예산 검사는 도구 호출 수를 먼저 증가시킨 뒤 HTTP 전송 예산을 확인하므로 도구 3, HTTP 2다. 별도 cancel 제어 요청 1회는 Target 요청이 아니다. 소유자/proof 이상은 네트워크 오류가 아니라 11-step workflow 완료 후 **확정 판정의 대조 조건이 부족함**을 뜻한다. 새 proof가 Worker의 사전 commitment와 매칭되지 않아 뒤쪽 안정성 reason까지 진행하지 않고 `OWNER_RESOURCE_PROOF_UNPROVEN`이 나왔다. 이를 기대 verdict에 맞춰 고치거나 대상별 특례로 우회하지 않았다.

실행된 14개 run 모두 최초 판정과 저장 증거 replay가 일치했다. 정책 사전 거절 2개는 replay 대상이 없다. 회수 시 14개를 별도로 다시 replay해 일치를 확인했다. issued plan 16개, claimed 14개와 실패 run을 모두 보존한다.

## 설정만으로 연결된 부분과 추가 코드

전용 설정으로 `/gateway/authenticate`의 `handle/secret`, `/gateway/session/profile`의 `context.member.subject`, `/workspace/attachments/{resource_id}`의 중첩 ID/owner/string visibility/proof, cookie `project_sid`와 Bearer `session.grant.credential`을 연결했다. 기존 tickets/documents 이름·경로·응답 형태를 사용하지 않는다. agent의 `lab-web`, `user-a/user-b`, 네 secret reference 이름만 v1의 고정 논리 별칭이다.

대상은 표준 라이브러리 HTTP 서버, 별도 Member/Attachment 모델, 프로젝트 구성원 ACL, 메모리 session 저장소를 구현했다. 기존 target/fixture/TargetStore/canary helper를 import하거나 상속하지 않는다. 기존 FastAPI fixture의 경로 이름만 바꾼 복제도 아니다. 서버 모듈은 agent 코드 의존성이 없다.

추가 코드는 `validation/independent_api/`의 대상·설정·TCP Worker lifecycle, 반복 행렬 스크립트, 회귀 테스트와 문서다. Controller/Worker/계약/verifier 및 운영 `config/targets*.json`은 기준 커밋 대비 동일하다. 대상별 verifier 분기나 계약 확장은 없다. [운영·재현 문서](../../docs/independent_api_validation.md)에 매핑과 명령을 기록했다.

## 비밀값과 기존 환경 보존

비밀번호·proof·cookie/Bearer 세션·Worker token은 실행마다 새로 생성해 메모리에만 보유했다. proof 변경 시험의 새 proof와 정책 변경 Worker의 새 proof도 검사 대상에 포함했다. 공개 전 staging의 모든 JSON/Markdown을 실제 생성값 총 **114개**와 대조했고 각 case `publication_check.json`의 matches는 0이다. 의도적으로 비밀값을 산출물에 넣는 회귀 테스트는 output 복사 전에 실패하는 것을 확인한다.

공개 내용은 plan/snapshot/commitment, 실행 identity, 정제 증거 및 횟수다. 원본 응답 본문·credential·raw proof·서버 로그·DB는 저장하지 않았다. `target_measurement.json`은 operation/status/count만 기록하며 verifier가 읽는 run 폴더 밖에 둔다. `SHA256SUMS.json`은 새 공개 파일의 byte를 확인하는 목록이며 인증 서명은 아니다.

기존 환경파일/DB/VM/방화벽/공유 폴더에 접근·배포·설정 변경을 수행하지 않았다. 이전 보고서는 수정하지 않는다. 실제 VM 배포/복구 성공이나 UI 브라우저 검증을 이번 결과로 주장하지 않는다.

## 회귀와 빌드

신규 집중 테스트 **26개 통과**, 전체 `.\.venv\Scripts\python.exe -m pytest`는 **799 passed, 20 warnings, 257.72초**였다. frontend의 `npm run build`도 성공했다(18 modules, 593ms). 기존 documents/records/operator-resource 및 배포 회귀를 포함한다. 이 개수는 위 실제 TCP 16건의 대체 증거가 아니다. 전체 회귀 안의 TCP 재실행 결과를 공개 행렬 건수에 중복 가산하지 않았다.

경고는 Pydantic 설정 forward-reference, 기존 MCP client deprecation, pytest cache 경로 쓰기 거절이다. 경고를 없애려고 의존성/기존 환경 권한을 변경하지 않았다. UI는 수정하지 않았고 실제 브라우저 검증은 수행하지 않았다. [verification_summary.json](verification_summary.json)에 명령·결과·보존 범위를 기록했다.

## 제약과 다음 작업

하나의 새 API에 대한 white-box 설정 적용이다. 기존 계약은 고정 두 계정·두 문자열 ID, 마지막 한 개의 동적 경로, object-key selector, 사전 합성 proof, 정확한 JSON 거절, HTTP IP literal와 cookie/Bearer 로그인에 여전히 종속된다. 다중 project/resource 경로와 배열 selector는 지원하지 않으며 해당 거절을 회귀로 남겼다. 일반 파일 다운로드/HTML/SSO/CSRF/HTTPS 외부 사이트까지 검증하지 않았다.

음성 대조의 Bearer 반복, 정책 재조회와 첫 로그인 사이 race를 이 독립 API로 주입하는 시험, VM·UI·live OpenAI·Nmap/Playwright는 이번 행렬에서 미검증이다. A→B 교차 조회 한 방향의 고정 read flow이며 모든 ACL 조합을 포괄하지 않는다. 다음에는 독립 구현자가 제공한 같은 계약 범위의 API로 재현하고, 현재 표현할 수 없는 구조는 별도 계약 확장 과제로 검토할 것을 권한다.
