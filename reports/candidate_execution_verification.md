# 후보 preview/run 검증 — 2026-11-01

기준 원격 `codex/openapi-candidate-import`를 fetch하여 `9cca082` 최신 상태를 확인한 뒤 `codex/candidate-preview-run`에서 구현했다. 기존 RunEngine·MockModelProvider·function/MCP client·HTTP Verifier를 재사용한다. 새 운영자 정책 REST 조회는 모델 도구가 아니며 원래 네 도구 목록을 유지한다. 기존 VM/환경파일/DB는 변경하지 않았다. 새 의존성은 없다.

## 직접 실행한 새 TCP 8조합

명령: `.\.venv\Scripts\python.exe -m scripts.run_candidate_verification`. Windows의 기존 Python 3.12.14 환경에서 임시 loopback target/worker와 임시 target DB를 사용했다. controller는 후보 preview/run 함수에서 기존 engine으로 연결했고 function은 REST, MCP는 실제 Streamable HTTP를 사용했다. target middleware가 독립적으로 요청을 세었다. fixture mode는 harness의 설정 이력일 뿐 HTTP Verifier 입력이 아니다. DB/log reader는 호출되면 실패하도록 막았다.

모두 provider=mock, access-control-http, COMPLETED, 증거 7개, http_observation, 저장 증거 재판정 일치다. 각 preview의 target 요청 0회, run의 target 요청 9회·도구 10회를 확인했다. 정책 조회는 별도 preview 1회·run 1회다. plan의 실제 Worker snapshot과 report의 적용 snapshot이 일치했다.

[새 행렬 JSON](candidate_execution/matrix-948a35b72598.json)에 run/plan/candidate ID와 실제 관측 사용량을 기록했다. 각 plan JSON·Markdown과 run의 기존 report/evidence 및 candidate_execution.json 연결 기록을 보관한다. plan은 당시 시점의 만료된 검증 예제이며 발급 이력 없이 실행 권한을 부여하지 않는다. 임시 loopback origin이 포함되므로 VM snapshot과 같은 hash를 기대하지 않는다.

| API | Fixture mode | Transport | Verdict | Run / plan |
|---|---|---|---|---|
| documents | vulnerable | function | VULNERABLE | [run_146a70503c1c4378bd5e26e5c7329ca3](candidate_execution/run_146a70503c1c4378bd5e26e5c7329ca3/report.json) / [evidence](candidate_execution/run_146a70503c1c4378bd5e26e5c7329ca3/evidence.json) / [plan](candidate_execution/plan_42a8d295daea462b9e8f02ab7af556ed.json) / [link](candidate_execution/run_146a70503c1c4378bd5e26e5c7329ca3/candidate_execution.json) |
| documents | vulnerable | mcp | VULNERABLE | [run_3d3999135d004117ba06ed29d51e468a](candidate_execution/run_3d3999135d004117ba06ed29d51e468a/report.json) / [evidence](candidate_execution/run_3d3999135d004117ba06ed29d51e468a/evidence.json) / [plan](candidate_execution/plan_613bd8edcf864102a70faa834a8212f2.json) / [link](candidate_execution/run_3d3999135d004117ba06ed29d51e468a/candidate_execution.json) |
| documents | fixed | function | BLOCKED_BY_ACCESS_CONTROL | [run_687bc87608be49c4bb2c2f0d83153b88](candidate_execution/run_687bc87608be49c4bb2c2f0d83153b88/report.json) / [evidence](candidate_execution/run_687bc87608be49c4bb2c2f0d83153b88/evidence.json) / [plan](candidate_execution/plan_8ee3e6043c814baaae024723064c6aa4.json) / [link](candidate_execution/run_687bc87608be49c4bb2c2f0d83153b88/candidate_execution.json) |
| documents | fixed | mcp | BLOCKED_BY_ACCESS_CONTROL | [run_dd8478ae7d664d23bbf9e88023405854](candidate_execution/run_dd8478ae7d664d23bbf9e88023405854/report.json) / [evidence](candidate_execution/run_dd8478ae7d664d23bbf9e88023405854/evidence.json) / [plan](candidate_execution/plan_b7bb428e18b644fd8f1e0a56b35cfedb.json) / [link](candidate_execution/run_dd8478ae7d664d23bbf9e88023405854/candidate_execution.json) |
| records | vulnerable | function | VULNERABLE | [run_fff4fc4a76004601ae175e0a905b1034](candidate_execution/run_fff4fc4a76004601ae175e0a905b1034/report.json) / [evidence](candidate_execution/run_fff4fc4a76004601ae175e0a905b1034/evidence.json) / [plan](candidate_execution/plan_287df54eda724652adb2708037f8a769.json) / [link](candidate_execution/run_fff4fc4a76004601ae175e0a905b1034/candidate_execution.json) |
| records | vulnerable | mcp | VULNERABLE | [run_2ac82f15ce0f46dea94dd11a4e8471a6](candidate_execution/run_2ac82f15ce0f46dea94dd11a4e8471a6/report.json) / [evidence](candidate_execution/run_2ac82f15ce0f46dea94dd11a4e8471a6/evidence.json) / [plan](candidate_execution/plan_67637abbc3a840308154759c46631dd8.json) / [link](candidate_execution/run_2ac82f15ce0f46dea94dd11a4e8471a6/candidate_execution.json) |
| records | fixed | function | BLOCKED_BY_ACCESS_CONTROL | [run_cefb6dc2667c4498b7d8cb5a6564b3cd](candidate_execution/run_cefb6dc2667c4498b7d8cb5a6564b3cd/report.json) / [evidence](candidate_execution/run_cefb6dc2667c4498b7d8cb5a6564b3cd/evidence.json) / [plan](candidate_execution/plan_e5243896de464e56aad2a69b7500fe36.json) / [link](candidate_execution/run_cefb6dc2667c4498b7d8cb5a6564b3cd/candidate_execution.json) |
| records | fixed | mcp | BLOCKED_BY_ACCESS_CONTROL | [run_c1268198c0f24ef8bc977e38457c1401](candidate_execution/run_c1268198c0f24ef8bc977e38457c1401/report.json) / [evidence](candidate_execution/run_c1268198c0f24ef8bc977e38457c1401/evidence.json) / [plan](candidate_execution/plan_5c0b481a102c4f6c8f6b141fdd109652.json) / [link](candidate_execution/run_c1268198c0f24ef8bc977e38457c1401/candidate_execution.json) |

## 회귀와 실패 경계

집중 검사 `python -m pytest tests/test_candidate_execution.py tests/test_candidates.py --tb=short`: **213 passed, 5 warnings, 15.05초**. 기존 importer 164개를 포함하며 이전 결과와 더해 새로운 건수로 표현하지 않는다.

- preview에서 엔진·mock provider 호출을 금지하고 target HTTP 0회를 확인했다. 기존 importer의 socket/HTTP/OpenAI/subprocess/Uvicorn/SQLite 감시도 유지했다.
- 원본 변경·준비 상태 변경, 없는/중복 후보, 재해시한 plan의 transport/source/registry/candidate/정책/origin 변조, 만료·확인값 누락·불일치, 엄격한 plan 입력 상한·중복 JSON·NaN·extra/provider 변경을 거절했다.
- Worker 프로필·어댑터·전역 한도를 바꾼 정책 조회 및 조회 이후 재시작 경쟁을 구분했다. 새 Worker 인스턴스에 오래된 snapshot을 제출하는 function/MCP 실제 TCP 시험에서 target 요청 0회, run state 미생성을 확인했다. bound run에서 다음 세션의 binding 누락도 차단했다.
- 정책 조회의 WORKER_TOKEN·Controller 주소 경계, 구버전/잘못된 계약의 명시적 실패, 기존 네 MCP 도구 allowlist를 확인했다.
- 16개 동시 claim은 정확히 하나만 성공했다. 두 동시 run 요청도 엔진 실행/결과 디렉터리 하나만 허용했다. 로그인 실패·취소·timeout 후에도 plan을 재사용하지 못했다.
- 두 transport에서 허용 HTTP 2회 plan은 실제 전송 2회·도구 3회 뒤 SCOPE_LIMIT_EXCEEDED/INCONCLUSIVE였다. 이 정책 상한과 정상 예상 9회/10회를 구분했다.
- CLI parser/main을 preview→확인값 누락 거절→명시적 run까지 ASGI Worker로 시험했다. 부모의 잘못된 worker URL·OpenAI provider/key를 주입해도 명시한 controller 파일·mock만 사용했다. 이 CLI 시험의 target은 로그인 실패 대조군으로 exit 1/INCONCLUSIVE이며 정상 TCP 8조합과 별개다. 비밀값이 plan/출력에 없음을 확인했다.

전체 회귀 `.\.venv\Scripts\python.exe -m pytest --tb=short`: **545 passed, 11 warnings, 257.25초**. 기존 MCP/Pydantic 의존성 경고이며 실패는 없었다. 이후 테스트만 추가한 `test_full_run_policy_race_has_no_applied_policy`도 **1 passed, 4.60초**로 확인했다. 이 추가 시험은 전체 실행 수에 합산하지 않는다. 실제 실행 경로에서도 마지막 정책 경쟁이 HTTP 0회·도구 0회·INCONCLUSIVE로 끝나고 actual_scope_policy=null을 보존하는 것을 검사했다.

프런트엔드 `npm test`: **14 passed**, `npm run build`: **성공**. 브라우저 E2E 결과가 아니다. pytest 임시/캐시 경로는 기존 Windows 권한 문제를 피하도록 `PYTEST_DEBUG_TEMPROOT`을 verification_tmp의 절대 경로로, `PYTEST_ADDOPTS`를 `-o cache_dir=verification_tmp/pytest-cache`로 지정했다. 전체 회귀에 포함된 기존 TCP 시험은 유지했지만 기존 행렬 스크립트를 별도로 반복하지 않았다.

## 미검증과 다음 단계

새 경로의 VM 배포·실행, 브라우저/UI 승인 화면, 외부 서비스, 분산 plan 이력, OpenAI 실호출은 미검증/미구현이다. 신규 경로는 mock만 지원하며 유료 호출하지 않았다. 기존 사용자 VM 정상 8건과 이전 OpenAI 결과·실패 이력은 그대로 보존하고 이번 증거로 재사용하지 않는다. 새 어댑터 VM 정책 거절·한도 차단도 여전히 미검증이다.

plan 이력은 로컬 운영자가 보호하는 파일이다. 해당 이력 자체를 임의로 삭제·변조할 수 있는 주체를 막는 서명 시스템이 아니다. 기존 CLI와 같이 결과는 파일 기반이며 UI DB에 자동 등록되지 않는다. 강제 프로세스 종료/파일 쓰기 장애의 완전한 복구는 별도 검증하지 않았다. claim을 보존하고 새 preview로 복구한다.

다음은 운영자가 [VM별 업데이트·검토·실행 절차](../docs/candidate_preview_run.md)를 사용해 동일한 신규 경로를 확인하는 단계다. UI 연결은 그 이후 별도 작업이다.
