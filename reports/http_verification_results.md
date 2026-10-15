# HTTP 관측 검증 실행 결과 — 2026-10-15

## 변경과 실행 환경

- 기준 main: `17d72b8` (`origin/main` fetch 후 차이 0/0, 시작 당시 사용자 변경 없음).
- 실행한 구현 작업 트리를 그대로 담은 커밋: `b97baf9ba97dc62df2d5da5b35aab0670984e3f2`, 브랜치 `codex/http-verification`. 아래 테스트와 네 조합 실행 후 이 소스를 커밋했으며 이후 코드는 변경하지 않았다. 이 결과 문서/증거는 후속 문서 커밋으로 보존한다.
- 환경: Windows, Python **3.12.14**, Node.js **v22.18.0**, npm **10.9.3**. 기존 설치 패키지/lock 사용, 새 의존성 추가 없음.
- 기본 provider: **mock**. OpenAI 실호출 0회. target/worker는 임시 loopback TCP 서버, controller는 Python engine이며 REST function 및 SDK Streamable HTTP MCP를 각각 실제 호출했다.
- 최종 네 조합 실행: 2026-10-15 **23:12 KST**. 아래 시간은 KST이고 JSON의 원본 시간은 UTC다.

구현은 별도 `access-control-http` 시나리오, HTTP 전용 판정 함수, 독립 세션/소유 관계/private canary 비교/재조회, 제한된 증거 스키마와 보고서 기준, UI 선택, 양쪽 transport 전달 및 재현 스크립트를 포함한다. 기존 `access-control`의 로그 요구와 offline import는 유지한다. 임시 DB 정리를 위해 target의 SQLite 연결을 명시적으로 닫도록 수정했다.

## 최종 네 조합 — 실제 실행 및 정리 성공

명령: `.\.venv\Scripts\python.exe scripts/run_http_verification.py` (PowerShell에서 stdout/stderr를 git-ignore된 `verification_tmp/http-matrix-final.log`로 리디렉션하여 검사; 종료 코드 0).

원본 요약: [matrix-5cba34249eb5.json](http_verification/matrix-5cba34249eb5.json).

| fixture 모드 / transport | 실제 run ID 및 보고서 | 판정 | 증거 / HTTP / 도구 | 판정 기준 | 시작–종료 KST / 소요 |
|---|---|---|---|---|---|
| vulnerable / function | [http-96ba12ca5c0d4370aeb91b5aee48f0bc](http_verification/http-96ba12ca5c0d4370aeb91b5aee48f0bc/report.json) | `VULNERABLE` | 7 / 9 / 10 | `http_observation` | 23:12:16.559703–23:12:18.007167 / 1.447s |
| vulnerable / mcp | [http-6568a72b0e504b8cb3f6315c1c41b4f8](http_verification/http-6568a72b0e504b8cb3f6315c1c41b4f8/report.json) | `VULNERABLE` | 7 / 9 / 10 | `http_observation` | 23:12:21.281935–23:12:22.521438 / 1.240s |
| fixed / function | [http-4758cec4bc8d4ebcb5ddf206564b5e65](http_verification/http-4758cec4bc8d4ebcb5ddf206564b5e65/report.json) | `BLOCKED_BY_ACCESS_CONTROL` | 7 / 9 / 10 | `http_observation` | 23:12:23.888381–23:12:25.335792 / 1.447s |
| fixed / mcp | [http-6198113e474341d7ba256f5ad1696381](http_verification/http-6198113e474341d7ba256f5ad1696381/report.json) | `BLOCKED_BY_ACCESS_CONTROL` | 7 / 9 / 10 | `http_observation` | 23:12:25.635914–23:12:27.069869 / 1.434s |

각 run 폴더에 `report.json`, `report.md`, `evidence.json`을 함께 보존했다. 보고서의 target `mode`는 의도적으로 `unknown`, `target_server_log`는 `not_used`다. 표의 fixture 모드는 테스트 실행자가 구성한 모드이며 verifier 입력이 아니다.

판정 완료 후 **7/7 × 4회** target-local 기록과 요청/run/method/path/status/account/canary digest를 독립 대조했다. 이 대조는 스크립트의 사후 assertion이며 HTTP verifier나 모델 입력이 아니다. HTTP workflow의 `observation_reader`는 호출 시 실패하도록 주입했고 모든 판정이 성공했다. 최종 저장 evidence를 순수 HTTP verifier로 다시 읽어 **4/4 동일 판정**을 확인했다. 내보낸 모든 JSON/Markdown에서 비밀번호, 실제 쿠키, 불투명 세션 참조, Authorization, target 원문 문자열이 없음을 검사했다. 임시 DB와 서버 정리가 끝나야 matrix JSON을 기록한다.

## 회귀 테스트와 실제 명령

PowerShell에서 저장소 루트 기준:

```powershell
$env:PYTHONUTF8 = '1'
New-Item -ItemType Directory -Force verification_tmp | Out-Null
$env:PYTEST_DEBUG_TEMPROOT = (Get-Item verification_tmp).FullName
$env:PYTEST_ADDOPTS = '-o cache_dir=verification_tmp/pytest-cache'
.\.venv\Scripts\python.exe -m pytest
Push-Location frontend
npm test
npm run build
Pop-Location
```

| 검증 | 실제 결과 |
|---|---|
| 기존 main 독립 복사본 (`git archive main`, 별도 폴더에서 `python -m pytest --tb=short`) | **62 passed**, 4 warnings, 46.52초 |
| 최종 Python 전체 (`.\.venv\Scripts\python.exe -m pytest`) | **110 passed**, 6 warnings, 123.89초 |
| UI Node 상태 회귀/소스 계약 (`npm test`) | **12 passed**, 0 failed |
| TypeScript/Vite (`npm run build`) | 성공, 18 modules, Vite 8.3.4 |
| `git diff --check` 및 저장된 네 실행 증거 재검증 | 통과 |

최종 Python 경고는 Pydantic settings의 unresolved forward reference 1개와 기존 MCP transport helper deprecation 5개다. 실패나 skip은 없다. React 검증은 **Node 상태 테스트 및 소스 계약 검사**이며 실제 브라우저 E2E가 아니다.

| 지침 ID | 검증 내용/근거 |
|---|---|
| HTTP-01/02 | 실제 loopback TCP 네 조합 및 `test_http_controls_dynamic_canaries_and_privacy` |
| HTTP-03 | 교차 요청 403 미인증, 증거의 만료 계정 표시, 사후 A 통제 실패 → INCONCLUSIVE |
| HTTP-04 | 소유자 실패/소유 관계 누락/목록 소유자 불일치/목록 중첩 → INCONCLUSIVE |
| HTTP-05 | 로그인 HTML 200, 공통/공개 응답과 전체 해시 단독 일치, 인증 헤더가 있는 일반 403 HTML/JSON 오류도 INCONCLUSIVE |
| HTTP-06 | timeout/전송 오류/65,536B 초과/요청·도구 예산 초과, finish 예산 부족 → INCONCLUSIVE; 한도 유지 |
| HTTP-07 | A/B 문서 ID 및 canary를 변경한 두 모드 모두 정답 하드코딩 없이 구별 |
| HTTP-08 | 중복 ID/request/purpose, 혼합 run, 계정/리소스/세션/순서 불일치 거절 |
| HTTP-09 | 외부 origin redirect는 따라가기 전에 차단; 전송에 기록된 URL이 등록 origin에만 존재. 기존 URL 정규화 정책 테스트도 통과 |
| HTTP-10 | 기존 `test_core_flow`/`test_verifier_hardening`의 로그 없는 경로 INCONCLUSIVE 유지 |
| HTTP-11 | 기존 offline digest/import/API 갱신 테스트와 UI refresh 테스트 통과; 새 HTTP 결과에 offline import는 409 |
| HTTP-12 | controller DB·이벤트·보고서의 정제 데이터, 모델 입력이 등록 scenario/target 두 값뿐임을 확인; 예외 문자열의 비밀/원문 미전달, 내보낸 파일 검사 |

테스트 구현: [test_http_verification.py](../tests/test_http_verification.py), [기존 API 회귀](../tests/test_controller_api.py), [UI 계약 검사](../frontend/tests/security-contract.test.mjs).

## 실패/중간 실행 이력 — 삭제하거나 최종 성공으로 덮어쓰지 않음

1. 최초 필수 Python 명령은 `.venv`가 삭제된 Python 3.12.10 경로를 참조해 시작하지 못했다. 설치된 bundled Python 3.12.14로 `.venv`를 복구했다. 프로젝트 코드/비밀 파일은 이 복구에 포함되지 않았다.
2. 복구 직후 기본 Windows temp 경로 접근 문제로 **36 passed / 26 setup errors**가 발생했다. `PYTEST_DEBUG_TEMPROOT`를 workspace 내부에 두어 해결했고, main 독립 복사본은 62개 전부 통과했다. 수정 초기 회귀도 62개 통과했으나 기존 `.pytest_cache` ACL 경고가 있어 별도 cache_dir로 옮겼다.
3. 최초 네 조합은 예상 판정을 만들었으나 Windows에서 열려 있는 SQLite 연결 때문에 마지막 임시 DB 정리에 실패했다. 해당 스크립트 실행은 **실패**로 기록한다. 같은 수정 전 코드를 이미 로드한 최초 새 테스트 실행은 **42 passed / 1 failed**, 실패는 동일한 cleanup 오류였다. target 연결의 명시적 close 수정 후 재실행했다.
4. 연결 수정 후 전체 **108 passed**. 이후 인증된 공통 오류 응답을 거절하기 위한 `response_kind` 검사 및 두 오류 사례를 추가했고 최종 **110 passed**가 위 결과다.

아래 네 파일은 최초 cleanup 실패 당시의 **개발 중 기록**이다. 최종 `response_kind`/목록 소유 증거 강화 이전 형식이므로 현재 verifier의 최종 증거로 재해석하지 않는다. 원본 파일을 보존하며 완료 주장은 위 final matrix만 사용한다.

- vulnerable/function: [http-a96432cacd774ab985c8d0b87ab70d32](http_verification/http-a96432cacd774ab985c8d0b87ab70d32/report.json) — cleanup 실패 실행의 중간 산출물.
- vulnerable/mcp: [http-d50049a44708441096cd2be0932ac459](http_verification/http-d50049a44708441096cd2be0932ac459/report.json) — cleanup 실패 실행의 중간 산출물.
- fixed/function: [http-fe541702a2e54e00af0dbb7593fc9436](http_verification/http-fe541702a2e54e00af0dbb7593fc9436/report.json) — cleanup 실패 실행의 중간 산출물.
- fixed/mcp: [http-d5e08044fdcb439fbf76425c930bd7af](http_verification/http-d5e08044fdcb439fbf76425c930bd7af/report.json) — cleanup 실패 실행의 중간 산출물.

## 미검증과 다음 작업

- Windows 로컬 소켓의 mock 네 조합만 직접 검증했다. **Ubuntu 실행, 실제 VM 네 조합, VM 격리 설정, 실제 브라우저 E2E, OpenAI 실호출은 미검증**이다.
- 일반 사이트 HTML의 의미 비교, 임의 외부 대상, 모델 학습, Nmap, Playwright, 자동 제보는 추가하지 않았다. MAC/NIC/방화벽/RAM/CPU와 배포 target registry는 변경하지 않았다.
- worker가 관측한 HTTP 메타데이터와 명시적인 합성 타겟 계약을 신뢰하는 실험이다. 보고서 digest는 동일성 확인이지 위조 방지 서명이나 독립 감사 증명이 아니다. 결과는 해당 계정/문서/시점에만 적용한다.
- 다음 작업: [HTTP 실행 가이드](../docs/http_verification_runbook.md)의 VM 명령으로 두 모드 × function/MCP를 다시 실행하고 각 VM run ID/판정/basis/증거 수를 보존한다. 외부 테스트는 별도의 허용 프로그램 정책 작업 후 검토한다.
