# 운영자 검사 워크스페이스

운영자는 로그인 후 등록된 프로필과 function/MCP 연결을 선택하고, 구체적인 preview를 확인한 뒤 현재 계획을 한 번 실행할 수 있다. 저장 결과·HTTP 증거·별도의 DNS/TLS 관측·증거 재판정을 조회하고 Markdown/JSON 재현 보고서를 내려받는다. 기존 시나리오·채팅 화면도 유지한다.

## 권한과 기존 실행 경로

`controller.workspace`는 기존 `controller.operator_execution.preview/execute_plan`을 연결한다. CLI와 UI가 공유하는 `validate_execution`은 source/registry 재분석, digest, 발급 이력, 사용 여부, 만료, Worker origin 및 정책을 검사한다. 실제 실행기에서 이를 다시 검사하고 기존 issued/claimed 이력을 사용한다. Worker의 실행 전 snapshot 검사와 전송별 scope/TLS/DNS 검사는 변경하지 않았다. 새 검사 엔진, verifier 분기, 모델 도구, 새 Target API는 없다.

프로필은 서버 측 파일로만 등록한다. 브라우저 입력은 프로필 ID, function/MCP, 표시된 plan ID/digest와 명시적 확인에 한정한다. URL·origin·IP 범위·한도·CA·계정·provider override는 거절한다. provider는 mock 고정이다. 계정 별칭은 기존 계약의 `user-a`/`user-b`, 리소스는 운영자가 등록한 두 ID다.

준비 상태와 preview는 인증된 Worker 정책을 조회하고 로컬 명세/registry를 분석한다. Target 로그인이나 연결 성공 확인이 아니다. UI 준비 상태는 페이지 조회 시점의 관측이며, 권한은 매 preview/run의 Worker 검사로 결정한다. 정책 변경 후에는 서버 측 파일을 일치시키고 화면을 다시 연 다음 새 preview를 확인해야 한다.

## 서버 측 준비와 실행

1. 기존 operator-resource-v1 계약에 맞는 두 계정·두 비공개 읽기 리소스, 인증/identity/detail 경로와 제한된 JSON selector를 준비한다. OpenAPI 명세와 Worker가 사용하는 정확한 registry 사본을 Controller에서 읽을 수 있게 한다. 계정 비밀번호와 raw proof는 Worker 전용 환경에만 둔다.
2. Worker의 등록 origin, 허용 경로, IP/CIDR, 한도 및 필요 시 `TARGET_CA_BUNDLE`을 기존 절차로 설정한다. CA 파일/비밀번호를 Controller 프로필에 넣지 않는다. HTTPS는 검증을 유지하고 도메인은 DNS 전체 결과 검사와 연결 IP 고정을 유지한다.
3. 운영자 전용 디렉터리에 다음 형식의 JSON을 만든다. 아래 경로는 설명용 placeholder이며 배포 설정을 추가하거나 수정한 것이 아니다. 상대 경로는 이 JSON의 디렉터리를 기준으로 해석한다.

```json
{
  "schema_version": "operator-workspace-v1",
  "profiles": [{
    "profile_id": "prepared-resources",
    "name": "운영자가 준비한 리소스 검사",
    "source_path": "./prepared-api.openapi.json",
    "registry_path": "./approved-worker-registry.json"
  }]
}
```

4. Controller 전용 환경에 `OPERATOR_WORKSPACE_CONFIG`를 지정한다. 필요하면 `OPERATOR_WORKSPACE_STATE_PATH`를 별도 영속 디렉터리로 지정한다(기본 `data/operator_workspace`). 기존 Controller의 `reports/runs` 아래에 run 산출물을 저장한다. `WORKER_URL`/`WORKER_TOKEN`은 기존 Controller 설정을 재사용하며 하나의 설정된 Worker만 사용한다. 여러 프로필은 그 Worker 정책과 각각 일치해야 한다. 프로필은 최대 16개이며 불일치 프로필로 fallback하지 않는다.
5. 기존 `common.service_config check/serve controller --env-file ...` 절차로 검증/실행한다. 정확한 명령 형식은 `python -m common.service_config --help` 참조. UI origin/host/client allowlist와 기존 로그인 설정을 유지한다. 이 작업에서는 기존 환경파일·DB·VM에 위 절차를 적용하지 않았다.

워크스페이스 설정을 생략하면 미설정 안내와 기존 채팅 이동을 제공한다. 파일들은 운영자 전용 쓰기 권한으로 보호한다. state와 reports를 함께 백업한다. 파일 journal은 기존 DB 스키마를 변경하지 않는다.

## 실행·복구 보장과 한계

- preview에는 origin, 계정/리소스 조합, 11개 요청 순서, 예상 HTTP 11/도구 12, 정책/TLS/DNS, plan ID/digest/만료를 표시한다. 확인 체크와 실행 버튼을 분리한다.
- 서버는 제출 receipt를 배타적으로 생성한다. 동시 요청은 최대 한 번 승인되고 기존 실행기의 atomic claim이 최종 단일 사용을 보장한다. 브라우저 재시도나 네트워크 오류에 POST를 자동 반복하지 않는다.
- 실행은 Controller background task로 유지된다. 브라우저는 plan/run ID만 sessionStorage에 저장하며 재접속 시 서버 이력으로 조회한다. 새 세션도 최근 제출/저장 검사에서 복구할 수 있다.
- **단일 운영자·단일 Controller 프로세스**가 지원 범위다. 다중 프로세스 작업 큐가 아니다. Controller 재시작 때 미완료 receipt는 `INTERRUPTED`로 남기고 자동 재시작하지 않는다. claimed run ID가 있으면 부분 증거를 조회한다. 새로운 검사가 필요하면 운영자가 기존 상태를 검토하고 새 preview를 승인한다.
- 결과 갱신 실패는 검사 실패와 분리한다. TLS/DNS/정책 문제는 안전 판정이 아니다. 실행 상태와 `VULNERABLE`/`BLOCKED_BY_ACCESS_CONTROL`/`INCONCLUSIVE`를 별도로 표시한다.
- 목록은 최근 제출 100개, 저장 보고서 200개로 제한한다. 알려진 유효 plan/run ID의 API 조회는 별도로 가능하다. 대규모 이력 탐색 UI는 이번 범위가 아니다.

## API와 비밀값 경계

모든 `/api/operator/*` 경로는 기존 Controller owner 인증을 사용한다. 기존 HttpOnly/SameSite=Strict 세션, POST의 Origin 및 세션 연결 CSRF header, host/client allowlist를 유지한다. UI 요청은 same-origin이며 no-store다. 인증정보를 URL/query나 다운로드에 넣지 않는다.

| API | 용도 |
| --- | --- |
| GET `/profiles` | 읽기 전용 준비 상태/정책 투영 |
| POST `/preview` | 등록 프로필/transport로 발급 |
| GET `/plans/{plan_id}` | 표시 계획과 제출 상태 복구 |
| POST `/plans/{plan_id}/run` | digest와 `confirmed: true` 검증 후 202 |
| GET `/jobs`, `/runs` | 영속 제출/검사 이력 |
| GET `/runs/{run_id}` | 저장 증거와 재판정 |
| GET `/runs/{run_id}/download/{markdown\|json}` | 고정 파생 산출물 다운로드 |

plan/run ID를 정규식으로 검증한다. 고정 파일명과 root containment 검사, symlink/junction 거절을 사용하며 서버 임의 파일 다운로드 기능은 없다. Worker의 원본 adapter/environment 참조/계정 로그인/비밀번호/proof commitment를 UI에 전달하지 않고 공개 별칭과 정책 snapshot만 투영한다. 원본 응답·cookie·Bearer·raw proof·개인키·CA 경로는 다운로드에 포함하지 않는다. React의 텍스트 렌더링을 사용한다.

## 보고서와 과거 기록

기존 저장 `operator-report-v1`, contract/evidence/connection 관측을 읽어 verifier replay를 실행한다. Markdown은 요약, 대상/시각/범위, 준비 조건, 요청 순서, 기대와 관측, evidence ID, 영향/한계, 권고, 재판정/버전의 9개 절로 구성한다. JSON에도 같은 정제된 데이터와 인증 placeholder를 제공한다. LLM을 호출하지 않고 원본 증거를 변경하지 않는다.

합성 proof의 일치는 실제 고객 데이터 유출로 표현하지 않는다. 심각도·금전 피해·사이트 전체 안전성을 생성하지 않는다. 과거 CLI operator 보고서에 실행 버전이 없으면 `not-recorded`로 표시한다. legacy documents/records 및 로그 기반 보고서는 기존 채팅 조회 경로를 유지한다. 기존 기록을 새 형식으로 덮어쓰지 않는다.

## 재현 명령과 검증 범위

```powershell
.\.venv\Scripts\python.exe -m scripts.run_operator_workspace_validation --output verification_tmp/workspace-new-run
# 실제 브라우저용 임시 환경. ready.json은 비공개이며 공개 보고서에 복사하지 않는다.
.\.venv\Scripts\python.exe -m scripts.run_operator_workspace_validation --output verification_tmp/workspace-new-browser --browser
.\.venv\Scripts\python.exe -m pytest
cd frontend
npm test
npm run build
```

출력 디렉터리는 새 경로여야 한다. 브라우저 모드의 고정 파일 제어는 **테스트 helper만** 읽는 `command.json`에 `{"action":"measure"}`, `fixed`, `policy_change`, `sync_profile`, `stop`을 순차 기록한다. 이는 UI/API/모델 도구가 아니며 같은 기존 첨부파일 API와 임시 Worker/Controller만 제어한다. `stop`은 정제 산출물 내보내기와 비밀값 대조 후 listener/임시 DB/인증서/키를 정리한다. 공개할 것은 `public/`의 검사된 산출물뿐이다.

실제 브라우저에서 function 취약 실행, MCP 수정 실행, 새로고침/기존 결과 재열기, 다운로드, 정책 변경 거절, 긴 증거의 접힘/내부 스크롤 및 기존 채팅 이동을 확인했다. 실제 Controller/Worker TCP와 Target TLS socket을 사용했으며 `.test` DNS는 코드 경계에서 주입했다. 운영체제 DNS, 외부 서비스, VM 배포, 다중 사용자/RBAC는 검증하지 않았다. API 응답 유실 회귀는 POST 응답 본문을 버린 뒤 ID로 복구하는 시뮬레이션이며 실제 회선 단절을 주장하지 않는다. 상세 실행 결과와 오류/수정 이력은 `reports/operator_workspace_20261115/`에 기록한다.

## VM 업데이트의 설정·이력 보존

`scripts.vm_deploy`는 workspace 설정이 있는 Controller에서 다음을 배포 계획의 hash에 포함한다.

- `OPERATOR_WORKSPACE_CONFIG`와 각 프로필의 `source_path`/`registry_path` 파일.
- `OPERATOR_WORKSPACE_STATE_PATH` 아래 issued/claimed 계획, bindings, 제출 receipts.
- 관련 `reports/runs` 파일과 기존 역할별 환경·DB·네트워크 관측.

환경의 상대 경로는 기존 checkout 기준, 프로필의 상대 경로는 workspace JSON의 디렉터리 기준으로 해석한다. 참조된 JSON 파일만 새 release의 `runtime-config/operator-workspace`로 복사하고 새 workspace JSON에서 상대 참조를 다시 만든다. 환경파일은 새 release에 파생본을 쓴다. 원본 파일을 수정하거나 이전 release의 설정을 조용히 계속 참조하지 않는다.

현재 지원 범위는 checkout 내부의 일반 JSON 참조 파일과 `data/` 아래 workspace state다. 외부 경로, `.git`/`.venv`/`node_modules` 참조, symlink/junction, 예상하지 않은 state 파일은 거절한다. 외부 설정이 필요한 운영자는 해당 서비스가 정지한 상태에서 별도로 검토한 내부 사본을 준비하고, 수정된 설정을 기준으로 새 inspect/plan을 만들어야 한다. 배포 도구가 외부 파일을 자동으로 따라가거나 복사하지 않는다.

서비스를 중지하기 전에 source/config/state/report 변경을 재검사한다. admission 경계가 새 preview/submit을 막은 상태에서 다시 검사하고 정상 SIGTERM을 수행한다. 진행 중/대기 중 작업이 있으면 `WORKSPACE_RUN_IN_PROGRESS`로 거절하며 강제 취소해 배포하지 않는다. 이전 workspace 코드에 이 경계가 없으면 실행 중 자동 배포를 거절하므로 먼저 운영자가 정상 종료해야 한다. `WORKSPACE_BUSY`/`WORKSPACE_MAINTENANCE`의 오래된 marker는 자동 제거하지 않는다. 재부팅이나 비정상 종료 후에는 원래 작업·listener·journal을 확인한 다음 운영자가 복구 경계를 결정한다.

배포 후 새로 발급/제출/소비되거나 변경된 workspace 기록이 있으면 수동 rollback을 `WORKSPACE_NEW_HISTORY_ROLLBACK_REFUSED`로 거절한다. 기존 서비스와 마지막 배포 상태를 유지하며 별도 감사 파일에 원인을 남긴다. rollback은 새 DB·보고서·실행 데이터를 이전 release에 자동 병합하지 않는다. 실제 변경을 시작한 뒤 복구에 실패한 경우에는 `RECOVERY_REQUIRED` 상태에서 운영자가 점검한다. [상태별 조회 방법](repeatable_vm_deployment.md#수동-rollback-결과-조회)

workspace가 없는 기존 배포는 같은 경로를 유지한다. 별도의 DB migration은 없다. 단일 Controller 프로세스 전제와 새 preview/digest 확인 규칙도 그대로다.

### 처음 준비하는 고정 실습 프로필

운영자 전용 `scripts.vm_deploy_host prepare-workspace --exchange <전달경로>`는 이미 등록된 HTTP `10.78.0.30:8080`, cookie, 두 계정·두 tickets 리소스만 준비한다. 기존 예제 명세/registry와 같은 내용인지 guest에서 재확인한다. 새 비밀번호/proof는 private 전달 파일에만 저장하며 Controller 로그인 키와 Worker token은 기존 환경에서 보존한다. 기존 Target DB를 사용하는 서비스를 수정하는 대신 별도 `operator-target` 환경과 기존 독립 API launcher를 새 release에서 사용한다. DNS/CA/HTTPS를 추가하지 않는다.

이 설정은 자동 기본값이 아니다. 명시적으로 준비한 `workspace-setup`의 파일 hash가 계획에 들어가며, 준비 파일이 바뀌면 apply 전에 새 계획을 요구한다. `prepare-fixed`는 준비된 동일 비밀값을 유지하고 Target의 시험 모드만 fixed로 바꾼다. 이 변경도 새 plan/digest/apply와 정상 재시작을 거친다. 일반 업데이트에서는 새 setup을 넣지 않고 현재 프로필/환경을 보존한다.

### 고정 역할 서비스 명령

새 active checkout에서 `python -m scripts.vm_service status`로 고정 역할 주소의 health를 확인한다. `start`, `stop`, `restart`에는 확인한 40자리 `--expected` commit이 필요하며, 실제 hostname의 등록 역할과 active checkout만 사용한다. 임의 shell/URL/port를 받지 않는다. Controller restart도 workspace가 idle일 때만 허용하고 기존 DB·journal·reports를 그대로 사용한다. 이 명령은 systemd나 부팅 자동 실행을 설치하지 않는다.

### 2026-11-16 적용한 실습 VM 사용법

세 VM에 `ubuntu`로 로그인한다. 각 VM의 active checkout은 `/home/ubuntu/securityaiagent-deployments/active.json`의 `checkout` 값이다. 11월 16일 최종 Controller는 `releases/f64a9a332e04447b8fd31167c62d7a43`, Worker는 `releases/582d58d5c84a4859b358ec04ec3b4dc4`, fixed Target은 `releases/2c6a3ad1c48040278e8dbcf52445e027`이었다. 세 경로의 상위 디렉터리는 `/home/ubuntu/securityaiagent-deployments`다.

재부팅 후 Target → Worker → Controller 순서로 각 VM에서 실행한다. 이미 서비스가 실행 중이면 먼저 status로 확인한다. sudo 인증은 기존 방화벽을 읽는 데 사용한다.

```bash
sudo -v
cd "$(python3 -c 'import json; print(json.load(open("/home/ubuntu/securityaiagent-deployments/active.json"))["checkout"])')"
expected=97d10e25298261775bc4423dab1d6226ed22a156
.venv/bin/python -m scripts.vm_service start --expected "$expected"
.venv/bin/python -m scripts.vm_service status
```

호스트에서 [실습 UI](http://192.168.56.10:8000/)를 열어 기존 Controller 접근 토큰으로 인증한다. 준비된 프로필을 선택하고 preview의 대상과 계획을 확인한 뒤 실행한다. 제출 응답이 끊기면 **기존 상태 조회**에서 해당 제출을 연다. 기존 검사와 보고서는 **저장된 검사**에서 다시 열 수 있다.

종료 시 진행 중인 제출이 끝났는지 확인한다. Controller → Worker → Target 순으로 위와 같은 checkout에서 `.venv/bin/python -m scripts.vm_service stop --expected "$expected"`를 실행한다. 다음 기동에도 같은 start 절차를 사용한다.

업데이트할 때는 새 exchange에 오프라인 bundle을 준비하고 역할별 inspect에서 관측한 commit을 plan의 expected로 지정한다. 프로필이 이미 구성된 일반 업데이트는 기존 설정을 승계한다. 새 release 경로, 참조 파일 해시, state 및 보고서 목록을 검토한 뒤 해당 plan ID와 digest로 apply한다. 복구할 때도 원래 plan의 ID와 digest를 사용한다. 결과가 누락되면 같은 sequence의 receipt와 journal을 먼저 조회한다. [배포 절차와 관측 결과](../reports/operator_workspace_vm_20261116/README.md)
