# records 후보 preview → 계획 확인 → run: 실제 VM 검증

2026-11-05 KST에 Codex가 기존 세 실습 VM에서 **`controller.candidates`와 `controller.candidate_execution`의 실제 CLI**를 실행했다. 2026-11-04의 `controller.cli` 검사를 반복하거나 그 결과를 재사용하지 않았다. 두 전송 모두 mock / `access-control-http` / 등록 `lab-web`이며, 기존 records 정책과 환경을 유지했다.

## 결과

| 항목 | function | MCP |
|---|---|---|
| preview CLI exit | 0 | 0 |
| preview 대상 요청 | **0회** — 관찰 구간 target 방향 TCP 패킷 0개 | **0회** — 관찰 구간 target 방향 TCP 패킷 0개 |
| preview 관찰 시간 | 02:01:11.978–02:01:44.323 KST, 32.344초 | 02:02:19.295–02:02:51.193 KST, 31.898초 |
| 별도 run CLI exit | 0 | 0 |
| 실행 시간(KST) | 02:01:52.406–02:01:56.512 | 02:03:00.960–02:03:05.138 |
| 상태 / 판정 | COMPLETED / VULNERABLE | COMPLETED / VULNERABLE |
| 실제 사용량(Worker 보고) | HTTP **9회**, 도구 **10회** | HTTP **9회**, 도구 **10회** |
| 정책 조회(연결 기록) | preview **1회** + run **1회** | preview **1회** + run **1회** |
| 증거 / basis | **7개** / `http_observation` | **7개** / `http_observation` |
| plan→claim→link→report 정책·identity 연결 | 일치 | 일치 |
| 저장 증거 재판정 | VULNERABLE, 보고서와 일치 | VULNERABLE, 보고서와 일치 |

실패한 preview/run은 없었다. VULNERABLE은 현재 합성 계정·리소스·관찰 시점의 HTTP 증거 판정이며 사이트 전체 판단이 아니다. 현재 설정을 바꾸지 않았으므로 다른 target 모드·documents·거절 정책 조합을 이번 VM 검증 결과로 주장하지 않는다.

## 실제 명령과 별도 계획 확인

모든 VM의 애플리케이션 HEAD는 `ef25892aafd4c0dc243d45d95cbe6ce6118c978d`였다. Windows 저장소의 직전 `a53558a`는 이전 배포의 결과 문서 커밋으로 애플리케이션 차이는 없다. 세 VM이 꺼진 상태였으므로 기존 설정으로 기동하고 사용자가 Ubuntu 로그인과 sudo 인증을 수행했다. 시작 전 상태를 보존한 다음 기존 `.env.<role>`을 사용하는 `common.service_config serve`로 서비스를 기동했다. 앱 코드·환경파일·정책·계정·NIC·방화벽을 수정하지 않았다.

controller에서 먼저 실제 importer를 실행했다:

```bash
.venv/bin/python -m controller.candidates import-openapi \
  --input examples/openapi/records.json --registry config/targets.records.json \
  --target lab-web --output verification_tmp/candidate_vm_20261105/public/records-candidates.json
```

[원본 catalogue](vm_candidate_20261105/records-candidates.json)는 `READY_FOR_REVIEW` 후보 1건을 반환했다:

- 후보 ID: `38eae30a50bfb3b8b5cebc483cd96e63b9cd712af75c798eecf59f0413273b89`
- 후보 경로: `GET /api/records/{document_id}`, 어댑터 `synthetic-records`
- 원본 bytes SHA-256: `89e170210a5f7247629ae30ccb21149464d3f9bcec2cfa84c5a6d67ef1219eb8`
- 정규화 registry SHA-256: `13809a7ef19def29fe700becb7ee40b6b5310164d32ac84221f6efe59ec9f654`

이어 각 전송별로 `controller.candidate_execution preview`를 별도 프로세스로 호출했다. 입력은 원본 records 명세와 registry이며 catalogue를 실행 권한으로 입력하지 않았다. preview 완료 후 Codex가 회수된 실제 plan JSON을 읽어 아래 내용을 검토한 다음, 다음 도구 호출에서 **그 plan의 정확한 digest를 리터럴 인자로 제공**했다. preview와 run을 자동으로 한 호출 안에서 연결하지 않았다. 사용자의 요청에 따라 Codex가 계획을 검토한 것이며, 사람이 별도 UI에서 plan 승인 버튼을 눌렀다는 의미는 아니다.

공통 검토 내용은 등록된 `lab-web` / `http://10.78.0.30:8080`, `user-a`·`user-b`, mock provider, records Bearer 인증, POST `/api/session`, GET `/api/me/records`, GET `/api/records/{document_id}`, HTTP 9회·도구 10회 상한, 5분 유효기간, 아래 Worker snapshot이었다. 두 plan의 transport가 각각 function/MCP인지도 확인했다.

```bash
# TRANSPORT, PLAN_FILE, DIGEST는 아래 실제 발급값을 각각 사용했다.
.venv/bin/python -m controller.candidate_execution preview \
  --input examples/openapi/records.json --registry config/targets.records.json \
  --target lab-web \
  --candidate-id 38eae30a50bfb3b8b5cebc483cd96e63b9cd712af75c798eecf59f0413273b89 \
  --transport TRANSPORT --env-file .env.controller --output PLAN_FILE

# plan 파일을 읽고 검토한 뒤 별도 명령으로 실행
.venv/bin/python -m controller.candidate_execution run \
  --input examples/openapi/records.json --registry config/targets.records.json \
  --plan PLAN_FILE --confirm-plan-sha256 DIGEST --env-file .env.controller
```

| 전송 | plan / 명시한 digest | 실제 run |
|---|---|---|
| function | [plan_51d2d6a7e6fc494e9f285a80efe29416](vm_candidate_20261105/function-plan-a52ac851.json), `326874f1f924d748a1a0247a6953629cfe5745932affba48cf4e10e358e1f71c` | [run_cfa57f69d5434ed3b556ae6d26e1bff4](vm_candidate_20261105/run_cfa57f69d5434ed3b556ae6d26e1bff4/report.json) |
| MCP | [plan_246cecf502c54c1aae2c26f674373ce5](vm_candidate_20261105/mcp-plan-b4475b32.json), `cf45e81976235d341fc0e526c5530bee1b418bf54e273f26fdc216e994932a1b` | [run_0f312e10632045ae99aa71b22e14921c](vm_candidate_20261105/run_0f312e10632045ae99aa71b22e14921c/report.json) |

CLI 인자·출력 수집·별도 run·검증에 사용한 [실제 VM 보조 스크립트](vm_candidate_20261105/vm_cli_harness.py.txt)를 보관했다. 이 스크립트는 `controller.cli`를 호출하지 않으며 run digest는 호출자가 별도 인자로 주어야 한다. 원래 후보 CLI의 발급·원본 재분석·정책 재조회·claim 처리를 우회하지 않았다. 명령 stdout/stderr 전체는 controller VM 내부에만 남기고 정제된 산출물만 회수했다.

## preview 대상 요청 0회의 확인 방법

[수동 계수 결과](vm_candidate_20261105/packet-counts.json)와 [실제로 실행한 계수 코드](vm_candidate_20261105/passive_counter.py.txt)를 보관했다. worker에서 검증된 registry의 target origin과 실제 route를 읽어 `enp0s8`, `10.78.0.20 → 10.78.0.30:8080`에 대한 AF_PACKET 수동 관찰을 실행했다. 네트워크 요청을 생성하거나 방화벽·서비스·정책을 바꾸지 않았다.

계수기가 해당 phase 진입을 확인한 뒤에만 preview CLI를 시작했다. 각 preview가 완료되고 plan이 회수된 뒤 run phase로 전환했다. 두 preview 구간 모두 target 방향 TCP 패킷·payload 포함 패킷·payload byte가 0이었다. 전체 capture의 socket drop은 0이었다. 이후 동일 계수기에서 function/MCP 실행 구간 각각 target 방향 TCP **65개**, payload 포함 **11개**, payload byte **3,189**를 관찰했다. 이는 계수기가 실제 실행 트래픽을 관측하는 양성 대조다.

따라서 위 구간에서 등록 target으로 향하는 preview HTTP 요청은 0회로 확인한다. 계수기는 패킷 내용을 저장하거나 HTTP 본문·인증 헤더를 해석하지 않았으며 pcap도 만들지 않았다. **TCP 패킷 65개 또는 payload 패킷 11개를 HTTP 요청 수로 해석하지 않는다.** 실제 HTTP 9회·도구 10회는 Worker가 반환한 `report.limits_used`이고, 두 REST 정책 조회는 `candidate_execution.json.control_calls`에서 별도로 기록한 수다. MCP handshake/discovery를 이 수에 합산하지 않는다. 이 관찰은 지정된 VM 구간·시간의 근거이며 다른 경로나 독립된 전체 네트워크 감사를 의미하지 않는다.

## 실행 정책과 증거 연결

실제 Worker가 반환한 정책은 `lab-records-access-control`, revision **1**, snapshot SHA-256 **`6a4d512a0681ddfba1939075f50dd133c4a180b7b5271ef6d751b0dc9e32dfe4`**였다. registry 설정 digest와 실효 한도를 포함한 run snapshot hash를 혼동하지 않는다. 이 hash는 identity이며 서명이 아니다.

실효 한도는 HTTP 9회, 도구 10회, 요청 timeout 5초, run timeout 180초, 응답 65,536 bytes, 초당 2회, 동시성 1이다. 정상 예상 사용량과 실제 사용량 및 상한을 각각 구분해 확인했다.

두 실행에서 다음을 비교했다:

1. 발급 이력 `.issued.json`과 실행한 plan의 전체 내용 일치.
2. 명시한 digest, `.claimed.json`의 digest/run ID, 실행 연결의 plan ID/digest 일치.
3. candidate ID, source bytes digest, registry digest의 plan/실행 연결 일치.
4. plan의 Worker 정책 = `candidate_execution.json.expected_scope_policy` = `actual_scope_policy` = 실제 `report.scope_policy`.
5. 원본 정제 `evidence.json`을 `Evidence`로 파싱하고 `verify_http_access_control(..., run_id=...)`로 재판정하여 보고서 판정과 일치.

직접 확인 가능한 연결·증거:

- function: [검증 요약](vm_candidate_20261105/controller-run-function.json), [실행 연결](vm_candidate_20261105/run_cfa57f69d5434ed3b556ae6d26e1bff4/candidate_execution.json), [증거](vm_candidate_20261105/run_cfa57f69d5434ed3b556ae6d26e1bff4/evidence.json), [claim](vm_candidate_20261105/plan_51d2d6a7e6fc494e9f285a80efe29416.claimed.json).
- MCP: [검증 요약](vm_candidate_20261105/controller-run-mcp.json), [실행 연결](vm_candidate_20261105/run_0f312e10632045ae99aa71b22e14921c/candidate_execution.json), [증거](vm_candidate_20261105/run_0f312e10632045ae99aa71b22e14921c/evidence.json), [claim](vm_candidate_20261105/plan_246cecf502c54c1aae2c26f674373ce5.claimed.json).

첫 세션에 expected snapshot을 보내고 Worker가 로그인 전에 검사하는 기존 `BoundClient` 경로를 실제 후보 CLI로 실행했다. 이번 VM 작업에서는 정책을 바꾸지 않았으므로 **정책 변경 경쟁/거절의 VM 재현까지 검증한 것으로 확대하지 않는다**. target DB·로그·모드·고정 정답은 HTTP verifier 입력으로 사용하지 않았다. 아래 DB 보존 비교는 각 VM 내부의 운영자 보존 감사이며 실행 판정과 분리됐다.

## 보존과 정리

- [controller](vm_candidate_20261105/controller-final.json), [worker](vm_candidate_20261105/worker-final.json), [target](vm_candidate_20261105/target-final.json) 최종 비교가 모두 성공했다. `.env*`, `config/`, 기존 `reports/runs/`, 기존 `data/candidate_plans/` 파일의 SHA-256이 동일하다.
- 세 VM의 기존 SQLite 총 8개 모두 `quick_check=ok`, 기존 행 보존을 확인했다. DB backup은 해당 VM의 `verification_tmp/candidate_vm_20261105/private/`에만 있으며 raw target DB/log·환경 비밀값을 공유 폴더나 Git에 넣지 않았다.
- controller에 새 issued/claimed 이력 **4개**가 추가됐으며 삭제하거나 재사용하지 않았다. 결과는 CLI 파일 산출물이며 UI DB의 실행 목록에는 자동 추가되지 않는다.
- [계수 프로세스 정상 종료](vm_candidate_20261105/observer-stop.json)를 확인했다. 정제 결과 회수용 transient 공유 `securityai-candidate-results`는 마운트 해제 및 VirtualBox 매핑 제거를 완료했다. 원래 읽기 전용 `securityai-update` 공유는 그대로다.
- [정리 후 controller UI·health](vm_candidate_20261105/controller-health.json)는 모두 HTTP 200, health `ok`다. 현재 세 서비스는 계속 실행 중이다.

회수 후 Windows에서도 JSON 산출물 28개를 읽고 plan digest 재계산, 5분 유효기간 안의 실행, claim/link/정책 연결, preview 관찰 구간, 저장 증거 재판정과 보존 결과를 다시 대조했다. [산출물 일관성 검사 결과](vm_candidate_20261105/artifact-validation.json)는 모두 성공했다. 이 대조에는 새 target 요청이 없다.

이번에는 앱 코드·프런트엔드 변경이 없어 전체 pytest/build를 반복하지 않았다. 새 VM 후보 경로 두 건과 회수된 JSON/plan/증거의 일관성을 직접 검증했다. 이전 로컬 회귀 수를 이번 실행 수로 재사용하지 않는다. OpenAI 호출·Nmap·Playwright·외부 사이트·다른 API/target 모드 검증은 수행하지 않았다.
