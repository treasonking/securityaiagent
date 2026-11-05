# 운영자 지정 리소스 검증

`operator-resource-http`는 운영자가 준비한 두 계정·두 비공개 리소스만 검증하는 별도 CLI 경로다. 기존 `access-control`, `access-control-http`, candidate-preview-v1, documents/records와 그 증거 형식은 유지한다. `DocumentId`나 옛 canary 검사를 느슨하게 만들지 않았다. 새 경로는 mock 전용이며 LLM을 호출하거나 모델에 도구를 제공하지 않는다.

## 로컬 독립 검증

저장소 루트, Python 3.12에서 실행한다. 기존 가상환경을 사용하거나 새 환경에 잠금 의존성을 설치한다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-full.lock
.\.venv\Scripts\python.exe -m pytest
$stamp = Get-Date -Format yyyyMMdd-HHmmss
.\.venv\Scripts\python.exe -m scripts.run_operator_verification --output "verification_tmp/operator-$stamp"
```

출력 폴더는 새 경로여야 한다. harness는 동적으로 확보한 loopback TCP 포트에서 **독립 in-memory JSON API와 Worker**를 띄운다. 비밀번호·세션·proof는 매번 무작위 생성하고 메모리에만 보유한다. 기존 TargetStore/target DB/canary helper를 사용하지 않는다. 자신이 시작한 서버만 종료한다. VM, 기존 서비스, 환경파일, DB를 읽거나 변경하지 않는다.

정상 8조합은 cookie/Bearer × vulnerable/fixed × function/MCP다. 추가 8건은 두 전송 각각 예산 2회, 정책 재조회 이후 첫 로그인 직전 proof 변경, redirect, public 응답을 검증한다. preview 전후 독립 API 수신 계수를 비교하고 run의 양성 트래픽으로 관측이 작동함을 대조한다. 이 계수는 target HTTP 수신 횟수이며 패킷 캡처 수치는 아니다. Worker 카운터와도 비교한다.

## 등록 계약과 비밀 준비

예제: `config/targets.operator.json`, `examples/openapi/operator-cookie.json`, `examples/openapi/operator-bearer.json`, `config/operator.worker.env.example`.

- 승인 origin은 HTTP IP literal 하나다. DNS/HTTPS/redirect/임의 URL을 추가하지 않는다. 원본 OpenAPI의 origin 선언은 등록 origin과 같아야 한다.
- schema 2.0의 별도 profile/revision과 `operator-resource-v1` adapter만 사용한다. profile의 승인 route와 adapter route가 정확히 같아야 한다.
- 논리 별칭은 `user-a`, `user-b`, target은 `lab-web`이다. 실제 principal은 예제의 `alice-17`, 문자열 `2048`처럼 별도 등록한다. 로그인 이름도 worker registry에서 지정한다.
- 리소스는 각 계정당 정확히 하나다. 예제는 UUID와 `ticket_2048`다. ID/principal은 ASCII 영숫자·밑줄·하이픈 1~128자 문자열이다. 숫자 JSON ID, 점/슬래시/백슬래시/인코딩/쿼리/Unicode는 거절한다.
- 리소스 경로의 마지막 한 세그먼트만 치환한다. `/me` principal 및 리소스 ID/owner/private/proof selector는 제한된 object-key 경로다. 배열 탐색, JSONPath, 스크립트는 없다.
- 공개/비공개 값과 명시적 거절 status/field/value를 등록한다. 거절은 지정한 JSON 객체 전체와 정확히 같아야 한다. 일반 403/404, HTML, WAF 응답은 차단 성공의 근거가 아니다.
- cookie 로그인은 OpenAPI에 `Set-Cookie` 응답을, Bearer는 token selector를 선언한다. `/me`와 resource 응답은 필요한 필드를 required로 명시한다. 지원을 입증하지 못하면 `NEEDS_CONFIGURATION`이다. description/example/default는 입력 증명이나 권한으로 쓰지 않는다.

운영자가 소유한 비공개 테스트 리소스의 일반 JSON 필드(예: `memo`)에 계정마다 다른 무작위 proof를 **검사 전에** 넣는다. 이 앱은 리소스를 생성·수정하지 않는다. 최소 128비트의 난수성을 확보하고 이름/개인정보/짧은 제목을 사용하지 않는다. 권장 생성 방법은 Python의 `secrets.token_urlsafe(32)`로 각각 별도 생성하는 것이다(256비트 난수). 지원 형식은 URL-safe ASCII 32~128자다. 길이 검사만으로 난수성을 증명할 수는 없다.

기대 proof는 Worker 전용 `OPERATOR_PROOF_A`, `OPERATOR_PROOF_B`에 넣는다. 로그인 비밀번호는 `LAB_USER_A_PASSWORD`, `LAB_USER_B_PASSWORD`다. registry/계획에는 환경 참조 이름만 넣는다. 두 proof가 같거나 누락·형식 오류면 Worker 설정 검사가 실패하고 실행되지 않는다. 두 리소스 응답의 proof가 같거나 A 응답에 B proof가 있으면 실행 판정은 `INCONCLUSIVE`다. 새 worker는 admin 자격증명을 필요로 하지 않는다.

Worker snapshot에는 정규화된 registry, 고엔트로피 proof의 domain-separated SHA-256 commitment, 고정 순서와 실효 한도가 들어간다. proof 원문을 snapshot에 직렬화하지 않는다. evidence에는 **정확히 기대 값과 일치한 경우만** run별 digest·일치 별칭을 남긴다. 임의 응답 전체 해시를 취약 판정에 쓰지 않는다. proof 변경은 worker 재시작 후 snapshot을 바꾸므로 이전 계획은 무효다.

## Preview → 계획 확인 → run

아래는 승인된 신규 환경에서 resource Worker가 실행 중일 때의 운영자 명령이다. 현재 VM에 자동 적용하는 명령이 아니다. `.env.controller`는 controller 전용 검사를 통과해야 하며 Worker와 같은 `WORKER_TOKEN`/origin을 사용한다. proof/로그인 비밀번호를 controller 파일에 넣지 않는다.

```powershell
$py = '.\.venv\Scripts\python.exe'
$stamp = Get-Date -Format yyyyMMdd-HHmmss
$out = "verification_tmp/operator-review-$stamp"
New-Item -ItemType Directory -Path $out | Out-Null
& $py -m controller.candidates import-openapi --input examples/openapi/operator-cookie.json --registry config/targets.operator.json --target lab-web --output "$out/catalogue.json"
$catalogue = Get-Content "$out/catalogue.json" -Raw | ConvertFrom-Json
$candidate = $catalogue.candidates[0].candidate_id
& $py -m controller.operator_execution preview --input examples/openapi/operator-cookie.json --registry config/targets.operator.json --env-file .env.controller --candidate-id $candidate --transport function --output "$out/plan.json"
Get-Content "$out/plan.md"
```

preview는 인증된 Worker 정책 REST 조회 1회만 한다. 대상 `/me`나 login을 포함한 대상 HTTP는 **0회**다. 계획의 provider/transport, target origin, 두 principal/리소스, 11개 요청의 순서·경로, proof 방식, Worker profile/revision/snapshot, 실효 상한, TTL을 확인한다. source·registry를 같은 원본으로 유지한다. 아래 명령은 검토 후 별도 실행한다.

```powershell
$plan = Get-Content "$out/plan.json" -Raw | ConvertFrom-Json
& $py -m controller.operator_execution run --input examples/openapi/operator-cookie.json --registry config/targets.operator.json --env-file .env.controller --plan "$out/plan.json" --confirm-plan-sha256 $plan.plan_sha256 --approved-by human
```

Codex가 계획을 검토한 실행은 `--approved-by codex`를 사용한다. 이 필드는 승인 주체에 대한 운영 기록이고 사람 신원 인증은 아니다. digest도 서명이나 독립 승인 시스템이 아니다. MCP는 **새 preview**에 `--transport mcp`를 지정하고 새 계획을 확인하여 run한다. Bearer는 Bearer adapter를 별도로 등록하고 해당 OpenAPI를 사용한다. 계획의 transport를 편집해 재사용하지 않는다.

run은 원본 OpenAPI/registry를 다시 분석하고 인증된 Worker 정책을 다시 조회한다. TTL 300초, 발급 원본, 별도 confirm digest, worker origin/정책/proof binding을 대조한 뒤 로컬 ledger에서 원자적으로 한 번만 claim한다. 실패·취소 후에도 claim을 유지한다. ledger `data/operator_plans`를 지우면 단일 사용 보장을 잃으므로 보존해야 한다. claim 후 crash는 ledger에 남고 자동 재실행하지 않는다.

## 실행량과 증거

| 단계 | 대상 HTTP | 도구 |
|---|---:|---:|
| A/B login | 2 | 2 |
| A/B `/me` | 2 | 2 |
| A/B 자신의 지정 리소스 | 2 | 2 |
| A 세션으로 B 리소스 | 1 | 1 |
| B/A 자신의 리소스 재확인 | 2 | 2 |
| A/B `/me` 재확인 | 2 | 2 |
| Worker finish | 0 | 1 |
| 정상 합계 | **11** | **12** |

증거는 로그인 포함 HTTP당 1개, 정상 11개다. 정책 조회 preview 1회/run 1회는 별도 controller-worker 제어 호출이며 대상 HTTP/도구 수에 포함하지 않는다. MCP initialize/list/transport 제어 요청도 대상 HTTP가 아니다. 실패 시 cancel은 별도 제어 호출이다. 도구 카운터는 Worker가 승인하여 시작한 호출 수이며 한도에서 거절된 HTTP 단계의 도구 1회가 포함될 수 있다. 인증/파싱 실패로 evidence가 없는 target 요청도 요청 카운터에는 포함한다.

예제 실효 상한은 HTTP 11/도구 12, 응답 65536B, 요청 5초/전체 180초, 초당 2회, 동시 1개다. 실효값은 global/profile/scenario 최소값이다. global rate 0도 profile rate를 비활성화하지 않는다. Worker는 실제 send 직전 origin/method/path/account/session/순서/snapshot을 검사한다. 재시도와 redirect 추적이 없다. 범위 거절이나 미완료는 `INCONCLUSIVE`다.

독립 cookie jar/Bearer session과 전후 `/me` principal이 identity 근거다. Worker의 무작위 session binding은 같은 실행 세션의 연결용 메타데이터이며 token hash로 identity를 추측하지 않는다. owner/id/private/proof 제어가 모두 맞고 안정된 B proof가 A의 교차 조회에 나타나야 `VULNERABLE`이다. 정상 전후 제어 아래 교차 응답만 정확한 명시적 거절이면 `BLOCKED_BY_ACCESS_CONTROL`이다.

```powershell
# run 출력의 run_id로 대체한다.
& $py -m verifier.operator --run-dir reports/runs/run_REPLACE_WITH_RETURNED_ID
```

`report.json`, `evidence.json`, `verification_contract.json`, `candidate_execution.json`을 보존한다. 새 verifier는 target DB/log/mode/fixture 정답을 읽지 않는다. 저장된 Worker 계약·정제 evidence·완료/사용량 연결로 재판정한다. `operator-report-v1`/`operator-evidence-v1`은 기존 보고서와 별도이며 옛 보고서는 기존 verifier로 재판정한다. 완료 확인이 없는 crash/timeout/failure는 11개 evidence가 있어도 확정 판정으로 올리지 않는다.

## 별도 VM 적용 단계와 한계

이번 구현·검증은 **로컬만** 수행한다. 기존 VM의 NIC/firewall/코드/환경/DB를 변경하지 않는다. 추후 VM 적용 승인을 받을 때 다음 사항을 별도 검토한다.

1. 새 branch commit을 별도 checkout에 배치하고 새 registry와 `.env.worker.operator`를 준비한다. 기존 `.env.worker` 및 DB를 덮어쓰지 않는다. 운영자가 대상 서비스의 두 테스트 리소스를 사전 준비한다.
2. 신규 파일만 검증한다: `.venv/bin/python -m common.service_config check worker --env-file .env.worker.operator`.
3. 승인된 전환 시간에 기존 Worker 프로세스의 포트 사용이 종료된 뒤 `.venv/bin/python -m common.service_config serve worker --env-file .env.worker.operator`로 새 Worker를 기동한다. launcher의 기존 bind/port는 유지된다. 이 문서는 현재 서비스 중지 명령을 자동 실행하지 않는다.
4. 별도 controller CLI에서 새 source/registry로 preview 후 계획을 검토하고 run한다. target DB 마이그레이션이나 reset은 이 앱의 단계가 아니다. 되돌릴 때는 기존 checkout/worker 환경으로 재기동하고 새 ledger는 보존한다.

한 Worker는 선택한 registry 계약의 도구만 노출한다. 기존 registry이면 기존 기능을 유지하고, operator registry이면 새 resource 도구만 노출한다. 기존 UI/LLM/시나리오를 새 Worker로 자동 변환하지 않는다. 새 경로는 CLI 전용이며 controller DB/UI 이력 통합은 하지 않았다.

결과는 등록된 두 리소스와 관찰 시점에 한정한다. 운영자 준비 proof를 사용하는 방식이며 합성 값 없이 일반 사이트 의미를 이해하는 탐지기가 아니다. 악성 서버의 거짓 `/me`/owner 응답, 로컬 계약·증거 전체 변조, operator ledger 삭제, 분산 승인, TLS/외부 IdP는 보장하지 않는다. proof commitment는 저엔트로피 값을 안전하게 만들지 않는다. Nmap/Playwright/유료 OpenAI 호출은 이번 범위에 없다.
