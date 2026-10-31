# 후보 선택 → 미리보기 → 명시적 mock 실행

이 경로는 `lab-web` / `access-control-http`의 운영자 등록 documents/records 읽기 흐름 하나를 실행한다. OpenAPI 후보를 임의 endpoint 탐색이나 새로운 취약점 판정 엔진으로 바꾸지 않는다. provider는 항상 **mock**이고 function/MCP만 선택한다. 기존 독립 UI/CLI의 OpenAI 기능은 그대로다.

## 경계와 파일

1. importer는 원본 로컬 명세·registry에서 후보를 다시 계산한다. catalogue 파일을 입력받지 않는다. ID가 없거나 정규화 후 중복이거나 READY_FOR_REVIEW가 아니면 거절한다.
2. preview는 Worker의 `GET /v1/operator/candidate-policy`를 조회한다. 기존 WORKER_TOKEN 및 Controller 주소 allowlist를 적용하며 모델의 4개 도구에 추가하지 않는다. 검사 transport가 MCP여도 **제어 조회는 REST**다. target HTTP·모델·검사 엔진 호출은 없다. importer 자체의 오프라인 계약은 유지한다.
3. importer와 Worker가 동일한 `ScopeRegistry.config_digest`로 origin/profile/adapter를 정규화한다. 이 설정 digest와 Worker의 실효 한도가 포함된 run snapshot hash는 다른 값이다. 실제 startup registry에서 반환한 정책만 사용한다. 구버전 Worker는 `WORKER_UPDATE_REQUIRED`, 잘못된 응답은 `WORKER_CONTRACT_INVALID`로 실패하며 fallback하지 않는다.
4. JSON plan에는 후보/source/registry 식별값, worker origin, 승인 origin/경로, 인증 방식, 두 account ref, mock/transport, 실제 Worker profile/revision/실효 한도/snapshot, 5분 유효기간과 plan digest를 넣는다. 생성·만료 시각은 Unix UTC 초다. digest는 동일성 확인값이며 서명·인증 토큰이 아니다. 정상 예상 사용량 9 HTTP / 10 tools와 Worker 허용 상한을 별도 표시한다. 낮은 한도라면 실행은 INCONCLUSIVE가 될 수 있다.
5. run은 `--confirm-plan-sha256`을 명시해야 한다. 원본과 registry를 다시 분석하고 Worker 정책을 재조회한다. 입력·정책·transport/provider·worker origin·plan 내용 변경이나 만료를 거절한다. source digest는 원본 bytes이므로 공백·개행 변화도 새 preview가 필요하다.
6. 첫 세션 시작 요청에 계약 버전과 expected snapshot을 전달한다. Worker는 현재 snapshot과 비교한 뒤에만 run 세션 생성·로그인을 허용한다. 조회와 로그인 사이 재시작에도 변경된 snapshot이면 target 0회로 차단한다. 이후 run은 동일 snapshot에 묶인다. 기존 직접 실행은 이 optional binding 없이 호환된다.

plan 입력은 strict/extra=forbid, 중복 JSON 키·비유한 수 거절, 2 MiB·깊이 32 상한을 적용한다. 내부 파일 경로를 실행 지시로 읽지 않는다. 명세·plan에서 URL/리소스 ID/도구 인자를 엔진에 넘기지 않는다. 실행에는 고정 scenario/target과 기존 엔진이 얻은 합성 ID만 사용한다.

## 한 번만 실행하는 운영자 이력

새 별도 디렉터리 `data/candidate_plans/`에 `<plan_id>.issued.json`과 원자적 exclusive-create로 `<plan_id>.claimed.json`을 남긴다. 기존 DB는 사용하거나 수정하지 않는다. 발급한 원본과 입력 plan을 비교하므로 편집 후 digest만 다시 계산해도 실행되지 않는다. claim은 하나의 run_id에 연결되며 프로세스/동시 CLI 간에도 하나만 생성된다. 실패·취소·타임아웃·중단 후에도 소모된 plan은 재사용하지 않는다.

이력은 해당 저장소·호스트의 **운영자 소유 신뢰 데이터**다. 임의 입력 파일이나 공유 업로드 위치로 사용하지 않는다. 다른 호스트 간 분산 lock이나 이력 파일을 삭제·변조할 수 있는 로컬 운영자로부터의 보호 기능은 아니다. 이력을 보존하고 파일을 지워 재실행하지 않는다. 다른 저장소/호스트에는 발급 이력이 없어 plan만 복사해 실행할 수 없다.

결과는 기존 `reports/runs/<run_id>/report.json`, `evidence.json`, `report.md`에 저장한다. 별도 `candidate_execution.json`에 candidate/plan/source/registry digest, expected 정책과 **실제 보고서의 Worker 정책**, control_calls, 상태·verdict를 연결한다. 기대 정책을 실제 적용 정책으로 꾸미지 않는다. 기존 report schema·UI reader는 바꾸지 않았다. CLI run은 기존 CLI와 같이 UI의 DB 실행 목록에 자동 등록되지 않는다.

정상 control_calls는 preview 정책 조회 1회 + run 정책 조회 1회다. target 9 HTTP·10 tools에 더하지 않는다. MCP handshake/tool discovery는 기존 transport 제어이며 이 정책 조회 수에 포함하지 않는다. 네트워크 실패 전의 미완료 제어 호출까지 전역 집계하는 telemetry 기능은 아니다.

출력 JSON과 같은 basename의 Markdown을 생성한다. 부모 폴더는 운영자가 생성하며 기존 파일은 덮어쓰지 않는다. 부분 파일 쓰기/프로세스 중단이 발생하면 산출물을 확인하고 새 이름으로 preview한다. 실행 전 claim 이후 장애가 나면 이력을 보존하고 기존 run 및 `candidate_execution.json`을 확인한 뒤 **새 preview**를 만든다. 초기 연결 기록은 INTERRUPTED/INCONCLUSIVE이며 완료 시 실제 결과로 갱신한다. 취소·타임아웃에는 확정 판정을 만들지 않는다. 기존 엔진의 불완전 workflow는 COMPLETED라도 INCONCLUSIVE일 수 있으며 CLI는 성공 exit 0으로 표시하지 않는다.

exit 0: preview 생성 또는 완료된 확정 mock 판정. exit 1: 완료 보고서가 INCONCLUSIVE. exit 2: 입력·정책·인증·만료·중복·실행 오류/취소/타임아웃. argparse 누락 인자도 2다. KeyboardInterrupt/프로세스 강제 종료 시 OS 종료 코드는 다를 수 있으나 claim은 남는다.

## Windows PowerShell

저장소 루트, 기존 서비스별 `.env.controller`를 사용한다. Controller에 LAB 비밀번호를 복사하지 않는다. `WORKER_TOKEN`은 worker와 일치해야 한다. 아래 명령은 운영자가 추후 실행할 명령이며 이번 작업에서 VM에 적용하지 않았다.

```powershell
New-Item -ItemType Directory -Force verification_tmp | Out-Null
.\.venv\Scripts\python.exe -m common.service_config check controller --env-file .env.controller
.\.venv\Scripts\python.exe -m controller.candidates import-openapi --input examples/openapi/records.json --registry config/targets.records.json --target lab-web --output verification_tmp/records-candidates.json
$catalogue = Get-Content verification_tmp/records-candidates.json -Raw | ConvertFrom-Json
$catalogue.candidates
# 이 fixture의 후보 1건과 상태를 검토한 뒤 선택한다.
$candidateId = $catalogue.candidates[0].candidate_id
.\.venv\Scripts\python.exe -m controller.candidate_execution preview --input examples/openapi/records.json --registry config/targets.records.json --target lab-web --candidate-id $candidateId --transport mcp --env-file .env.controller --output verification_tmp/records-plan.json
Get-Content verification_tmp/records-plan.md
```

미리보기의 대상·읽기 경로·인증 방식·상한·digest를 검토한 뒤 **별도 명령으로** 실행한다. 5분이 지나면 새 preview가 필요하다.

```powershell
$plan = Get-Content verification_tmp/records-plan.json -Raw | ConvertFrom-Json
.\.venv\Scripts\python.exe -m controller.candidate_execution run --input examples/openapi/records.json --registry config/targets.records.json --plan verification_tmp/records-plan.json --confirm-plan-sha256 $plan.plan_sha256 --env-file .env.controller
```

## Ubuntu

```bash
mkdir -p verification_tmp
.venv/bin/python -m common.service_config check controller --env-file .env.controller
.venv/bin/python -m controller.candidates import-openapi --input examples/openapi/records.json --registry config/targets.records.json --target lab-web --output verification_tmp/records-candidates.json
cat verification_tmp/records-candidates.json
# CANDIDATE_ID를 위 JSON에서 검토한 candidate_id로 바꾼다.
.venv/bin/python -m controller.candidate_execution preview --input examples/openapi/records.json --registry config/targets.records.json --target lab-web --candidate-id CANDIDATE_ID --transport mcp --env-file .env.controller --output verification_tmp/records-plan.json
cat verification_tmp/records-plan.md
```

별도 명령에서 PLAN_DIGEST를 미리보기의 검토한 64자리 plan_sha256으로 바꾼다. 비밀값을 화면에 출력하거나 채팅으로 전달할 필요는 없다.

```bash
.venv/bin/python -m controller.candidate_execution run --input examples/openapi/records.json --registry config/targets.records.json --plan verification_tmp/records-plan.json --confirm-plan-sha256 PLAN_DIGEST --env-file .env.controller
```

documents는 명세를 `examples/openapi/documents.json`, registry를 `config/targets.json`으로 바꾼다. transport는 preview에서 function 또는 mcp를 선택하며 run에서 변경할 수 없다. output은 매 preview마다 새 이름을 사용한다. 기존 환경의 MODEL_PROVIDER/TOOL_TRANSPORT와 무관하게 이 경로는 mock 및 plan에 고정된 transport만 실행한다.

신규 CLI는 `--env-file`을 직접 엄격하게 검증하고 해당 파일에서 선택한 worker 주소·토큰·timeout만 사용한다. 부모 환경에서 이 값을 보충하지 않고 controller DB도 초기화하지 않는다. `common.service_config serve`처럼 자식 프로세스 전체 환경을 필터링하는 방식은 아니며 OS/runtime 환경까지 지우지는 않는다. 기존 직접 `controller.cli`/dotenv 실행에는 이 신규 경로의 계획·필수 확인·이력 검사가 없으므로 서로 혼동하지 않는다. 독립 OpenAI 기능은 변경하지 않았다.

## VM별 추후 적용

1. 연결된 저장소에서 `git fetch origin` 후 `git bundle create securityaiagent-candidate-preview.bundle origin/codex/candidate-preview-run`, `git bundle verify securityaiagent-candidate-preview.bundle`로 전달물을 만든다. 승인된 기존 전달 경로만 사용한다.
2. 각 VM에서 변경 사항을 보존하고 bundle verify 후 `git fetch ./securityaiagent-candidate-preview.bundle refs/remotes/origin/codex/candidate-preview-run:refs/remotes/origin/codex/candidate-preview-run`을 실행한다. 새 로컬 브랜치라면 `git switch -c codex/candidate-preview-run --track origin/codex/candidate-preview-run`; 이미 있다면 해당 브랜치에서 `git merge --ff-only origin/codex/candidate-preview-run`을 사용한다. `git rev-parse HEAD`로 동일 커밋을 확인한다.
3. Worker VM: 자신의 `.env.worker`를 유지하고 `common.service_config check worker --env-file .env.worker` 후 운영자가 기존 worker를 정상 종료·`serve worker`로 재시작한다. 이 단계가 startup 정책과 신규 binding 계약을 적용한다.
4. Controller VM: 기존 `.env.controller`를 유지하고 check 후 위 preview/run CLI를 사용한다. UI 소스는 바꾸지 않았으나 배포 빌드가 필요하면 `frontend`에서 `npm run build`를 수행한다. Controller 프로세스를 사용한다면 자체 check/serve 절차를 따른다.
5. Target VM: 기존 API style/mode·DB·비밀번호를 유지한다. 두 API/mode 전환이 필요할 때만 기존 [어댑터 절차](target_api_adapters.md)에 따라 운영자가 설정·재시작한다. 이번 기능은 target 변경을 요구하지 않는다.

새 기능의 VM 배포·실행은 **미검증**이다. 로컬 결과·남은 한계는 [검증 보고서](../reports/candidate_execution_verification.md)에 있다. UI 승인 화면·외부 사이트·자율 탐색·새 취약점 유형은 이번 범위에 없다.
