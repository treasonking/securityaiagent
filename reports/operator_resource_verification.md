# 운영자 지정 리소스 검증 — 2026-11-06 KST

## 변경과 실행 기준

- 기준: `codex/candidate-preview-run`의 `055abf1d9b1a83184bff9455b881015a8e2c00d4`에서 새 `codex/operator-resource-verification` 브랜치를 만들었다. main 병합·기존 VM 적용은 하지 않았다.
- 실행 코드: `06a8a63fba47a8a527a15a9cd3032f3f24d7ee0f`. 최종 TCP 실행 시작 시 작업 트리는 clean이었다. 이후 커밋은 정제 증거·문서 추가다.
- 새 `operator-resource-http` / `operator-resource-v1` 계약, 별도 plan/evidence/verifier, Worker 전용 proof 참조, 실제 `/me` principal 및 owner/private/proof 제어를 추가했다. 기존 전역 DocumentId/canary 판정은 변경하지 않았다.
- 환경: Python 3.12.14; Windows-10-10.0.19045-SP0; provider `mock`; 승인 주체 `codex`(사람 신원 인증 아님).
- 최종 TCP: 2026-11-05T18:47:09.617670+00:00 ~ 2026-11-05T18:47:31.654005+00:00 UTC, 22.046초. KST 2026-11-06 03:47:09 ~ 03:47:31.
- 독립 in-memory JSON API + Worker를 새 loopback TCP 포트에 기동했다. TargetStore/target DB/log/canary helper를 사용하지 않았다. fixture의 기대 모드는 행렬 비교에만 쓰고 verifier 입력에는 넣지 않았다.

## 명령과 회귀 결과

```powershell
.\.venv\Scripts\python.exe -m pytest -o addopts= --tb=short
cd frontend
npm run build
cd ..
.\.venv\Scripts\python.exe -m scripts.run_operator_verification --output reports/operator_resource/tcp-06a8a63
```

- 전체 pytest: **706 passed, 12 warnings, 210.97초**. UTC 2026-11-05 18:41:27 ~ 18:44:59 (명령 로그 파일 시각). 기존 546개에 새 160개를 추가한 실제 새 실행이다. 테스트 완료 후 같은 앱/테스트 소스를 위 코드 커밋으로 고정했다.
- 빌드: `tsc -b && vite build` 성공; Vite 8.3.4, 18 modules, 번들 단계 390ms. frontend 소스 수정은 없다.
- 경고: Pydantic 설정 forward reference 1개, 기존 MCP transport helper deprecation 10개, 기존 pytest cache 쓰기 권한 경고 1개. 실패는 없으며 의존성 업데이트와 캐시 경로 관리는 별도 사항이다.
- 새 경계 테스트: cookie/Bearer에 public·동일/누락/변경 proof·공통 오류·ID/owner 불일치, 동일 principal/session·identity 불일치·만료·로그인 실패, HTML/redirect/429/500/중복 키/타입/크기, 범위·경로·세션·payload 변조, 취소·타임아웃, 2회 예산, 24개 동시 claim, 계획 만료/변조/재사용/원본·리소스·proof·정책 변경, 실제 send gate 직전 정책 변경, importer 미지원, 비밀 비노출 및 서비스별 환경 분리를 검사했다.
- 기존 호환: 전체 기존 시나리오/provider/candidate v1 회귀와 더불어 저장된 documents/records × vulnerable/fixed × function/MCP 증거 8건을 기존 verifier로 다시 판정해 기존 결과와 일치했다. OpenAI 경로는 네트워크 없는 stub 회귀이며 유료 API 호출은 하지 않았다.

## 실제 TCP 정상 8조합

모든 preview 대상 수신 요청 **0회**, run은 **HTTP 11회 / 도구 12회 / 증거 11개**였다. Worker 반환 실제 profile/revision/snapshot/실효 한도는 계획과 같았다. 저장 증거 재판정은 8/8 일치했다. UUID와 `ticket_2048`, 실제 principal `alice-17`과 문자열 `2048`을 사용했고 전용 identity 헤더를 사용하지 않았다.

| 인증 | 모드 | 전송 | 기대 = 실제 | 상태 | 증거/계획/연결 |
|---|---|---|---|---|---|
| cookie | vulnerable | function | VULNERABLE | COMPLETED | [run](operator_resource/tcp-06a8a63/cookie-vulnerable-function-normal/runs/run_5c413526c9f04a2f84d59fc3b6465b8b/report.json), [evidence](operator_resource/tcp-06a8a63/cookie-vulnerable-function-normal/runs/run_5c413526c9f04a2f84d59fc3b6465b8b/evidence.json), [plan](operator_resource/tcp-06a8a63/cookie-vulnerable-function-normal/plan.md), [link](operator_resource/tcp-06a8a63/cookie-vulnerable-function-normal/runs/run_5c413526c9f04a2f84d59fc3b6465b8b/candidate_execution.json) |
| cookie | vulnerable | mcp | VULNERABLE | COMPLETED | [run](operator_resource/tcp-06a8a63/cookie-vulnerable-mcp-normal/runs/run_1c55d68ac6514c8787b945b649dbd704/report.json), [evidence](operator_resource/tcp-06a8a63/cookie-vulnerable-mcp-normal/runs/run_1c55d68ac6514c8787b945b649dbd704/evidence.json), [plan](operator_resource/tcp-06a8a63/cookie-vulnerable-mcp-normal/plan.md), [link](operator_resource/tcp-06a8a63/cookie-vulnerable-mcp-normal/runs/run_1c55d68ac6514c8787b945b649dbd704/candidate_execution.json) |
| cookie | fixed | function | BLOCKED_BY_ACCESS_CONTROL | COMPLETED | [run](operator_resource/tcp-06a8a63/cookie-fixed-function-normal/runs/run_6add52f56ec341909e59c1573c1ee4f9/report.json), [evidence](operator_resource/tcp-06a8a63/cookie-fixed-function-normal/runs/run_6add52f56ec341909e59c1573c1ee4f9/evidence.json), [plan](operator_resource/tcp-06a8a63/cookie-fixed-function-normal/plan.md), [link](operator_resource/tcp-06a8a63/cookie-fixed-function-normal/runs/run_6add52f56ec341909e59c1573c1ee4f9/candidate_execution.json) |
| cookie | fixed | mcp | BLOCKED_BY_ACCESS_CONTROL | COMPLETED | [run](operator_resource/tcp-06a8a63/cookie-fixed-mcp-normal/runs/run_0d48ecb32af44a0d83221b82fe6077c9/report.json), [evidence](operator_resource/tcp-06a8a63/cookie-fixed-mcp-normal/runs/run_0d48ecb32af44a0d83221b82fe6077c9/evidence.json), [plan](operator_resource/tcp-06a8a63/cookie-fixed-mcp-normal/plan.md), [link](operator_resource/tcp-06a8a63/cookie-fixed-mcp-normal/runs/run_0d48ecb32af44a0d83221b82fe6077c9/candidate_execution.json) |
| bearer | vulnerable | function | VULNERABLE | COMPLETED | [run](operator_resource/tcp-06a8a63/bearer-vulnerable-function-normal/runs/run_165a8227a6d343619dea7e086ae151a5/report.json), [evidence](operator_resource/tcp-06a8a63/bearer-vulnerable-function-normal/runs/run_165a8227a6d343619dea7e086ae151a5/evidence.json), [plan](operator_resource/tcp-06a8a63/bearer-vulnerable-function-normal/plan.md), [link](operator_resource/tcp-06a8a63/bearer-vulnerable-function-normal/runs/run_165a8227a6d343619dea7e086ae151a5/candidate_execution.json) |
| bearer | vulnerable | mcp | VULNERABLE | COMPLETED | [run](operator_resource/tcp-06a8a63/bearer-vulnerable-mcp-normal/runs/run_ae15e1f5359d4453a4c332d9b726ce44/report.json), [evidence](operator_resource/tcp-06a8a63/bearer-vulnerable-mcp-normal/runs/run_ae15e1f5359d4453a4c332d9b726ce44/evidence.json), [plan](operator_resource/tcp-06a8a63/bearer-vulnerable-mcp-normal/plan.md), [link](operator_resource/tcp-06a8a63/bearer-vulnerable-mcp-normal/runs/run_ae15e1f5359d4453a4c332d9b726ce44/candidate_execution.json) |
| bearer | fixed | function | BLOCKED_BY_ACCESS_CONTROL | COMPLETED | [run](operator_resource/tcp-06a8a63/bearer-fixed-function-normal/runs/run_008d7357a8bf4459a44028fd49a93fd9/report.json), [evidence](operator_resource/tcp-06a8a63/bearer-fixed-function-normal/runs/run_008d7357a8bf4459a44028fd49a93fd9/evidence.json), [plan](operator_resource/tcp-06a8a63/bearer-fixed-function-normal/plan.md), [link](operator_resource/tcp-06a8a63/bearer-fixed-function-normal/runs/run_008d7357a8bf4459a44028fd49a93fd9/candidate_execution.json) |
| bearer | fixed | mcp | BLOCKED_BY_ACCESS_CONTROL | COMPLETED | [run](operator_resource/tcp-06a8a63/bearer-fixed-mcp-normal/runs/run_dde4075db32146fd8481392a3919e0c6/report.json), [evidence](operator_resource/tcp-06a8a63/bearer-fixed-mcp-normal/runs/run_dde4075db32146fd8481392a3919e0c6/evidence.json), [plan](operator_resource/tcp-06a8a63/bearer-fixed-mcp-normal/plan.md), [link](operator_resource/tcp-06a8a63/bearer-fixed-mcp-normal/runs/run_dde4075db32146fd8481392a3919e0c6/candidate_execution.json) |

## 실제 TCP 거절·불충분 8건

두 전송에서 모두 기대한 `INCONCLUSIVE`였다. 실패 run도 report/evidence/계약/claim/link를 보존했다. `FAILED`는 harness 실패가 아니라 의도한 Worker 거절/전송 실패 상태다. 모든 preview 대상 요청 0회이며 저장 증거 재판정 8/8 일치다.

| 전송 | 조건 | 상태 | 실제 HTTP/도구/증거 | reason_code | 기록 |
|---|---|---|---|---|---|
| function | budget2 | FAILED | 2/3/2 | SCOPE_LIMIT_EXCEEDED | [run](operator_resource/tcp-06a8a63/cookie-vulnerable-function-budget2/runs/run_37c6869026644d81b2063e9b1b703bef/report.json), [재판정](operator_resource/tcp-06a8a63/cookie-vulnerable-function-budget2/replay.json) |
| function | prelogin_policy_change | FAILED | 0/0/0 | CANDIDATE_POLICY_CHANGED | [run](operator_resource/tcp-06a8a63/cookie-vulnerable-function-prelogin_policy_change/runs/run_8e966854da564a60a00f3435252c3bd8/report.json), [재판정](operator_resource/tcp-06a8a63/cookie-vulnerable-function-prelogin_policy_change/replay.json) |
| function | redirect | FAILED | 7/7/6 | TRANSPORT_OR_RESPONSE_ERROR | [run](operator_resource/tcp-06a8a63/cookie-vulnerable-function-redirect/runs/run_df032c7c4a544308a24f6bc0c3bc9283/report.json), [재판정](operator_resource/tcp-06a8a63/cookie-vulnerable-function-redirect/replay.json) |
| function | public | COMPLETED | 11/12/11 | OWNER_RESOURCE_PROOF_UNPROVEN | [run](operator_resource/tcp-06a8a63/cookie-vulnerable-function-public/runs/run_aa24babeb77a4959bbe17d834c2670e9/report.json), [재판정](operator_resource/tcp-06a8a63/cookie-vulnerable-function-public/replay.json) |
| mcp | budget2 | FAILED | 2/3/2 | SCOPE_LIMIT_EXCEEDED | [run](operator_resource/tcp-06a8a63/cookie-vulnerable-mcp-budget2/runs/run_a081339b332040d8a78ec5e976349a9c/report.json), [재판정](operator_resource/tcp-06a8a63/cookie-vulnerable-mcp-budget2/replay.json) |
| mcp | prelogin_policy_change | FAILED | 0/0/0 | CANDIDATE_POLICY_CHANGED | [run](operator_resource/tcp-06a8a63/cookie-vulnerable-mcp-prelogin_policy_change/runs/run_aceac4fca2f54068ae2e64f319acdf94/report.json), [재판정](operator_resource/tcp-06a8a63/cookie-vulnerable-mcp-prelogin_policy_change/replay.json) |
| mcp | redirect | FAILED | 7/7/6 | TRANSPORT_OR_RESPONSE_ERROR | [run](operator_resource/tcp-06a8a63/cookie-vulnerable-mcp-redirect/runs/run_0cf37f49139444aa8d061672bcde87c9/report.json), [재판정](operator_resource/tcp-06a8a63/cookie-vulnerable-mcp-redirect/replay.json) |
| mcp | public | COMPLETED | 11/12/11 | OWNER_RESOURCE_PROOF_UNPROVEN | [run](operator_resource/tcp-06a8a63/cookie-vulnerable-mcp-public/runs/run_ed695b3dd3ec4ec1a43bd92c3a33d644/report.json), [재판정](operator_resource/tcp-06a8a63/cookie-vulnerable-mcp-public/replay.json) |

- `budget2`: 두 login 후 세 번째 도구가 HTTP 예산에서 거절됐다. 대상 실제 수신은 정확히 2회다. 도구는 승인 후 HTTP 한도를 검사하므로 3회다.
- `prelogin_policy_change`: run의 정책 재조회 이후, 첫 도구가 Worker에 도착하기 전에 proof binding을 바꿨다. 두 전송 모두 로그인/대상 HTTP/도구 0회로 거절됐다. 실행 scope를 반환받지 않았으므로 actual_scope_policy는 null이며 계획 값을 실제 값으로 복사하지 않았다.
- `redirect`: 7번째 교차 요청의 302를 추적하지 않고 종료했다. 실제 HTTP 7회, evidence 6개다. Worker는 원문 예외를 숨기고 `TRANSPORT_OR_RESPONSE_ERROR`를 반환한다. 이 harness의 주입 원인은 redirect이고, 해당 일반 코드만으로 다른 환경의 원인을 단정할 수 없다.
- `public`: 전체 흐름은 완료됐지만 owner 제어 응답이 public이므로 private proof 조건을 충족하지 못해 `INCONCLUSIVE`다.

## 관찰·출처와 재판정

- [전체 기계 판독 행렬](operator_resource/tcp-06a8a63/matrix.json), [회귀/보존 확인](operator_resource/verification_summary.json), [파일 SHA-256 목록](operator_resource/checksums.json). 각 폴더에 원본 구조 OpenAPI/등록 설정, catalogue, plan JSON/Markdown, 별도 plan_review, 발급/claim 이력, run별 report/evidence/verification_contract/candidate_execution, replay를 보존했다.
- preview 계수는 독립 API의 수신 middleware를 실행 전후 비교한 값이다. run의 11개 양성 수신과 Worker 카운터로 관측을 대조했다. 패킷 캡처/VM 관측으로 주장하지 않는다.
- 정상 정책 제어 REST는 preview 1회 + run 1회다. MCP 초기화/전송 제어와 실패 시 cancel은 대상 HTTP/도구 수와 별개다. 재시도와 redirect 추적은 없다.
- fixture 비밀번호/토큰/proof는 실행 중 무작위 생성했다. 각 파일을 당시 실제 비밀값과 대조해 원문이 없음을 확인했다. 저장된 proof는 commitment 또는 일치한 run별 digest뿐이다. 본문 전체/대상 상태/정답은 verifier에 전달하지 않았다.
- 앱/테스트의 예기치 않은 실패는 이번 실행에서 없었다. 초기 개발 TCP smoke 및 16건의 성공 기록과 원래 테스트 로그는 로컬 `verification_tmp/operator-development-20261106`에 보존하고, GitHub에는 위 코드 커밋으로 실행한 최종 정제 기록을 싣는다.
- 게시 전 CLI 재판정 확인 중 첫 명령에 `run_`을 중복 붙여 존재하지 않는 경로를 전달했다. CLI는 `REPLAY_INPUT_INVALID`(exit 2)로 거절했고 실제 run 경로로 고친 호출은 `VULNERABLE`, `verdict_matches=true`(exit 0)였다. 대상 요청이나 저장 증거 변경은 없었다. [두 호출 기록](operator_resource/replay_cli_checks.json)을 보존했다.
- 첫 게시 후 Git blob 검증에서 자동 줄바꿈 정규화 때문에 241개 중 223개 파일의 원본 바이트 SHA-256이 달라진 것을 확인했다. `.gitattributes`에 증거 폴더 `-text` 규칙을 추가해 원래 실행 산출물 바이트를 보존했다. 최종 게시 blob 241개는 manifest와 일치하고, 16건의 OpenAPI 원본 바이트 해시도 각 계획과 일치한다. 실행/증거 내용이나 판정 알고리즘은 바꾸지 않았다.

```powershell
.\.venv\Scripts\python.exe -m verifier.operator --run-dir reports/operator_resource/tcp-06a8a63/cookie-vulnerable-function-normal/runs/run_5c413526c9f04a2f84d59fc3b6465b8b
```

재판정은 저장된 정제 evidence, Worker 계약, report의 완료/사용량 연결만 사용한다. archived plan은 증거용이며 만료되어 재실행할 수 없다. 새 실행은 반드시 새 preview를 발급한다.

## 보존 범위와 남은 리스크

- 기존 VM에 접속하거나 NIC/방화벽/서비스/환경파일/DB를 변경하지 않았다. 기존 `config/targets.json`, `config/targets.records.json`, `common/api_contract.py`, `common/schemas.py`, `verifier/http.py`, target 및 frontend 소스는 기준 커밋과 동일하다.
- 운영자 등록 두 리소스·관찰 시점에만 유효하다. 서비스 고정 SYN 구조 대신 운영자 준비 무작위 테스트 값을 사용하며, 일반 사이트 탐지기나 오탐 0%를 의미하지 않는다.
- 악성 서버의 거짓 identity/owner, 로컬 계약·증거 전체 변조, ledger 삭제, 분산 승인, TLS/외부 IdP는 보장하지 않는다. commitment/plan hash는 서명이 아니다. `codex` 승인 기록을 사람 인증으로 표현하지 않는다.
- VM 배포/외부 실제 API/브라우저 UI E2E/유료 OpenAI/Nmap/Playwright는 미수행이다. 새 경로는 CLI 전용이다. 한 Worker의 operator registry 선택은 새 도구만 노출하므로 기존 UI 경로와 동시 사용을 자동 지원하지 않는다.
- 다음 단계는 [운영 가이드](../docs/operator_resource_runbook.md)의 별도 VM 전환 영향 검토와 운영자 테스트 리소스 준비다. 이 작업에서 VM 전환을 실행하지 않는다.
