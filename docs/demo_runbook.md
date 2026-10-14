# Demo runbook

## Local preflight

저장소 루트에서 commit과 기본 회귀를 먼저 기록한다.

```powershell
git log -1 --oneline
.\.venv\Scripts\python.exe -m pytest
cd frontend
npm ci
npm test
npm run build
cd ..
```

기존 `.venv`가 다른 위치의 삭제된 Python을 가리키면 이를 성공으로 간주하지 않는다. 새 Python 3.12 환경을 만들고 `requirements-full.lock`을 설치한 뒤 다시 실행하며, 환경 실패 원인도 보고서에 남긴다.

로컬 합성 core는 VM·환경 파일·OpenAI 키 없이 실행할 수 있다. 같은 mode의 다음 실행이 target 관찰 로그를 초기화할 수 있으므로 각 run은 다음 실행 전에 평가한다.

```powershell
.\.venv\Scripts\python.exe scripts/run_local_core.py --mode vulnerable
.\.venv\Scripts\python.exe -m verifier.cli evaluate --run-dir reports/runs/<vulnerable-run-id> --local-evidence data/target-vulnerable.sqlite3
.\.venv\Scripts\python.exe scripts/run_local_core.py --mode fixed
.\.venv\Scripts\python.exe -m verifier.cli evaluate --run-dir reports/runs/<fixed-run-id> --local-evidence data/target-fixed.sqlite3
```

각 결과의 JSON에서 `evidence_count=5`, `correlated_count=5`, 기대 verdict를 직접 확인한다. verifier CLI는 `INCONCLUSIVE` JSON을 출력하고도 종료 코드가 0일 수 있으므로 종료 코드만으로 합격 처리하지 않는다.

## VM preflight and health paths

환경 파일은 각 역할 VM에만 두고 비밀값을 출력하거나 저장소에 추가하지 않는다. 세 health 확인은 시나리오 증거와 별도로 저장한다.

Controller VM:

```bash
curl --noproxy '*' --connect-timeout 3 --max-time 5 http://10.77.0.20:9000/health
curl --noproxy '*' --connect-timeout 3 --max-time 5 http://10.78.0.30:8080/health
```

Worker VM:

```bash
curl --noproxy '*' --connect-timeout 3 --max-time 5 http://10.78.0.30:8080/health
```

첫 번째와 세 번째 요청은 각각 worker와 target health가 응답해야 한다. Controller에서 target으로 보내는 두 번째 요청은 실패가 기대되지만, 단일 timeout만으로 UFW 원인이나 완전한 격리를 단정하지 않는다. NIC, route, forwarding, firewall 정책/counter, IPv6와 외부 egress는 [`network_setup.md`](network_setup.md)의 별도 검증이 필요하다. Health 응답은 서비스 간 인증 성공을 증명하지 않는다.

## Initial VM scenario sequence

1. [`network_setup.md`](network_setup.md)에 따라 세 VM의 snapshot, NIC, route, forwarding, firewall 정책과 counters를 저장한다.
2. [`environment_loading.md`](environment_loading.md)에 따라 역할별 `.env.target`, `.env.worker`, `.env.controller`를 각 VM에만 만든다. 비밀 파일은 커밋하지 않는다.
3. 최초 시나리오 검증이나 의도적인 fixture 초기화에서만 target 환경을 로드하고 `python -m target.cli reset`을 실행한다. `TARGET_MODE=vulnerable`과 대상 DB 경로를 확인한 뒤 시작한다.
4. worker와 controller를 역할별 `--env-file`로 시작한다. controller는 `--workers 1`을 유지한다.
5. controller의 별도 shell에도 `.env.controller`를 로드한 뒤 `python -m controller.cli doctor` 결과와 종료 코드를 저장한다. Uvicorn의 `--env-file`은 다른 shell에 적용되지 않는다.
6. UI에서 `APP_ACCESS_TOKEN`으로 로그인한 뒤 `lab-web`, `access-control`, `mock`, `function`을 실행한다.
7. 완료 후 evidence 5개, 결과 메시지, 새로고침 복원, 대화 전환의 stale-response 차단, 취소 후 다음 run 실행을 직접 확인한다.
8. 같은 mode에서 `mock` + `MCP`를 별도 실행한다.
9. target-local DB로 두 run을 reset 전에 각각 오프라인 평가한다. controller로 target DB를 복사하거나 평가를 위해 직통 경로를 열지 않는다.
10. vulnerable target을 중지한다. 실행 DB가 `data/vm-target.sqlite3`였다면 target 안에서만 `data/vm-target-vulnerable.sqlite3`로 보관 복사하고 파일 존재를 직접 확인한다. 실행 중인 SQLite 파일을 복사하지 않는다.
11. `TARGET_MODE=fixed`와 `TARGET_DATABASE_PATH=data/vm-target-fixed.sqlite3`를 설정하고 환경 로드 → 의도적 reset → 재시작 순서로 같은 function/MCP 절차를 반복한다.

| Mode | Transport | Online completion | Required offline verdict |
|---|---|---|---|
| vulnerable | function | completed; socket-separated run은 correlation 전 `INCONCLUSIVE`일 수 있음 | `VULNERABLE`, 5/5 |
| vulnerable | MCP | completed; socket-separated run은 correlation 전 `INCONCLUSIVE`일 수 있음 | `VULNERABLE`, 5/5 |
| fixed | function | completed; socket-separated run은 correlation 전 `INCONCLUSIVE`일 수 있음 | `BLOCKED_BY_ACCESS_CONTROL`, 5/5 |
| fixed | MCP | completed; socket-separated run은 correlation 전 `INCONCLUSIVE`일 수 있음 | `BLOCKED_BY_ACCESS_CONTROL`, 5/5 |

CLI run은 controller DB/UI에 등록되지 않는다. 정상 완료여도 correlation 대기 때문에 verdict가 `INCONCLUSIVE`이면 종료 코드 1을 반환한다. UI offline import 시험에는 UI에서 생성한 run과 정제된 `offline_verification.json`만 사용한다.

## Offline verification and import

각 run 직후, 다음 mode나 reset으로 넘어가기 전에 target-local DB에서 평가한다. 아래 명령은 target VM에서 실행하며 원본 DB는 target 밖으로 옮기지 않는다.

```bash
.venv/bin/python -m verifier.cli evaluate \
  --run-dir reports/runs/<run_id> \
  --local-evidence data/<mode-specific-target>.sqlite3
```

생성된 `offline_verification.json`의 `run_id`, `verdict`, `evidence_count`, `correlated_count`, `evidence_digest`, `warnings`를 확인한다. 최종 판정에는 5/5 correlation이 필요하다. Digest는 정제 evidence와 import payload의 identity 일치를 검사하지만 출처의 진실성을 단독으로 증명하지 않는다.

망 분리 때문에 target에서 controller로 직접 import하지 않는 경우, 원본 DB나 로그가 아니라 정제된 `offline_verification.json`만 승인된 수동 경로로 옮긴다. 그 파일을 가진 허용된 운영자 호스트에서 별도 `OFFLINE_VERIFICATION_TOKEN`으로 `/api/internal/offline-verification`에 POST한다. 이 토큰과 JSON 내용을 보고서·대화·Git에 넣지 않는다. import 후 UI의 run ID, 최종 verdict, 5개 evidence, `offline-correlated` 상태를 다시 확인한다. 이를 온라인 자동 correlation이라고 기록하지 않는다.

토큰 용도는 서로 분리한다.

- `APP_ACCESS_TOKEN`: Windows 웹 로그인 시작용
- `WORKER_TOKEN`: controller와 worker 사이 서비스 인증용
- `OFFLINE_VERIFICATION_TOKEN`: 신뢰된 evaluator 결과 import용
- `OPENAI_API_KEY`: live provider를 명시적으로 선택할 때 controller에서만 사용하는 API 키

## Normal shutdown and restart

정상 종료는 각 서버에서 `Ctrl+C`로 프로세스를 멈춘 뒤 VM에서 `sudo poweroff`로 수행한다. 꺼진 상태 snapshot은 복구용이며 매번 복원하지 않는다. 일반 재실행에서는 `target.cli reset`을 실행하지 않는다. 같은 DB 경로와 controller 설정을 유지해야 이전 run과 session 상태를 보존할 수 있다.

Target VM:

```bash
cd ~/securityaiagent
mkdir -p logs
set -a
source .env.target
set +a
.venv/bin/python -m uvicorn target.app:app \
  --env-file .env.target \
  --host 10.78.0.30 \
  --port 8080 \
  --no-access-log \
  --log-level warning \
  >> logs/target-server.log 2>&1
```

Worker VM:

```bash
cd ~/securityaiagent
.venv/bin/python -m uvicorn --factory worker.app:create_app_from_env --env-file .env.worker --host 10.77.0.20 --port 9000
```

Controller VM:

```bash
cd ~/securityaiagent
.venv/bin/python -m uvicorn --factory controller.api:create_app_from_env --env-file .env.controller --host 192.168.56.10 --port 8000 --workers 1
```

셸의 기존 환경변수는 dotenv보다 우선할 수 있으므로 provider나 mode를 바꿀 때 현재 프로세스 환경을 확인한다. 재시작 후 UI에서 마지막 결과가 복원되는지는 controller의 동일 `DATABASE_PATH`와 설정을 사용했을 때만 유효한 관찰이다. 일반 종료·재시작에서는 `target.cli reset`을 실행하지 않는다.

`--no-access-log`와 warning-level redirection은 target 터미널의 stdout 출력을 줄이는 운영 완화다. SQLite observations와 verifier evidence를 끄지 않으며, VM 멈춤의 근본 원인 해결이나 장시간 안정성 증거가 아니다. `logs/target-server.log`는 target-local 진단 파일로 유지하고 원문을 Git·모델·controller·공개 보고서에 넣지 않는다. 운영자는 target 안에서 파일 존재와 크기, 디스크 여유, 보존 기간을 확인한 뒤 필요한 최소 정보만 정제한다.

현재 문서화된 DB 역할은 다음과 같다.

| Purpose | Target-local path |
|---|---|
| fixed mock/live observations | `data/vm-target-fixed.sqlite3` |
| live vulnerable observations | `data/vm-target-live-vulnerable.sqlite3` |
| initial mock vulnerable observations | `data/vm-target.sqlite3` |
| requested mock vulnerable archive | `data/vm-target-vulnerable.sqlite3` |

경로를 바꾸거나 snapshot을 복원한 뒤에는 실행 전에 `TARGET_DATABASE_PATH`와 `git rev-parse HEAD`를 각 VM에서 기록한다. controller, worker, target이 같은 commit이라고 추정하지 않는다.

## Missing-observation and responsiveness checks

화면이 느리거나 응답하지 않으면 추가 run으로 안정성을 주장하지 말고 현재 프로세스를 정상 종료한 뒤 reset 없이 위의 출력 완화 명령으로 target을 재시작한다. worker와 target health를 확인하고, 해당 run ID가 현재 `TARGET_DATABASE_PATH`의 observations에 실제 존재하는지 target 안에서 확인한 다음에만 offline 평가한다.

- UI에 evidence가 있어도 target DB에 해당 run observations가 없으면 offline 0/5 또는 `INCONCLUSIVE`를 성공으로 바꾸지 않는다.
- 재시작 뒤 observations가 사라졌다면 재시작을 정상 삭제 원인으로 단정하지 않는다. DB 경로, 초기화, snapshot, 저장 실패를 별도로 조사한다.
- worker slowdown과 target freeze는 CPU·메모리·프로세스·디스크·kernel 자료 없이 같은 원인으로 묶지 않는다.
- 운영 로그 원문 대신 run ID, DB 경로, observation count, health 결과와 정제된 오류 코드만 검증 기록에 남긴다.

## 2026-10-14 reported VM example

사용자가 제공한 기록에서는 `mock` provider로 vulnerable/fixed × function/MCP 네 조합을 각 1회 실행했고 모두 target-local 5/5 대조 후 정제 결과를 수동 import했다. 네 run ID와 digest, 확보 상태는 [`current_verification.md`](../reports/current_verification.md)와 [`evidence_index.md`](../reports/evidence_index.md)에 기록한다. 이 문서 수정은 Codex가 VM에서 해당 시나리오를 재실행했다는 뜻이 아니다.

## Live OpenAI candidate check

Live provider는 고정 workflow를 바꾸지 않고 후보 가설만 제안한다. 허용 후보 이름은 `cross_account_document_access` 하나이며, 후보는 user-b 본인 대조군과 user-a의 user-b 소유 비공개 문서 접근 가능성을 시험할지 나타낸다. 모델은 실제 HTTP 응답, target 로그, target mode, 정답 또는 verifier fixture를 받지 않고 최종 verdict를 결정하지 않는다. 후보가 없어도 고정 시나리오 도구 workflow와 증거 기반 verifier는 계속 실행된다.

의도적인 빈 목록은 성공 후보로 보충하지 않는다. 보고서에는 원본 모델 응답이나 전체 추론 대신 `EMPTY_CANDIDATES` 진단과 “접근 통제 판정은 별도 증거 기반” 안내만 남긴다. 비허용 후보 이름은 구조화 출력 검증 실패이며, API 실패와 함께 정상 빈 결과로 바꾸거나 mock으로 대체하지 않는다.

첨부 가이드에 기록된 첫 live run `run_8d464c88140f447d9fd7a794136545d4`는 수정 전 fixed/OpenAI/function 실행이다. API 1회와 토큰 사용량, 후보 `[]`, offline `BLOCKED_BY_ACCESS_CONTROL` 5/5 및 수동 import가 보고됐지만, 수정 전 필터의 입력은 남아 있지 않아 원래 빈 목록과 비허용 이름 제거를 사후 구분할 수 없다. 이전 report를 수정하거나 후보를 재구성하지 않는다.

첨부된 2026-10-15 가이드는 수정 후 live 대표 4조합이 완료됐다고 기록한다. fixed/function `run_0c128a3c7c0743798c27d2a2830468e5`, fixed/MCP `run_ea64269013f44d5793dadccda43dcc31`, vulnerable/function `run_b58e5aece9d7496396c45205f3dc6046`, vulnerable/MCP `run_4aa1b9b6e7fe4e0487af9ee1eeeb1ea0`이며, 모두 canonical 후보 1개와 offline 5/5 및 UI import가 보고됐다. run별 usage, digest와 파일 확보 상태는 [`current_verification.md`](../reports/current_verification.md)와 [`evidence_index.md`](../reports/evidence_index.md)에 기록한다. Codex는 해당 VM 파일을 직접 검사하지 않았다.

`run_20b9caa5720b4b1dbcb6d9a6a034a009`는 target observation이 없어 offline 0/5였고, `run_4139a4ebe3ed4208ac624e80f447e518`는 offline 결과와 usage가 없어 성공으로 세지 않는다. 마지막 `run_4aa1...`는 이들과 별도의 성공 run이다. 따라서 대표 성공 4조합을 전체 시도 100% 성공으로 표현하지 않는다.

향후 live 재검증은 controller를 업데이트하고 재시작한 다음 현재 mode DB를 reset하지 않은 채 조합별로 한 번씩 실행한다.

1. controller에 `MODEL_PROVIDER=openai`, 명시적 `OPENAI_MODEL`, 로컬 보호된 `OPENAI_API_KEY`가 설정됐는지 확인한다. 키 값을 출력·복사·보고하지 않는다.
2. UI에서 `lab-web`, `access-control`, OpenAI와 기록할 transport를 명시해 한 번 실행한다.
3. 새 run ID, model ID, status, model usage, 후보 목록, `EMPTY_CANDIDATES` 진단 또는 후보 source, warnings와 evidence 수를 기록한다.
4. 빈 목록이 다시 나와도 후보를 삽입하지 않고 verifier 절차를 계속한다. API/스키마 오류면 run 실패 상태를 그대로 기록한다.
5. 현재 mode에 대응하는 target DB로 offline 대조한 뒤 5/5일 때만 정제 JSON을 수동 import하고 UI의 최종 verdict와 `offline-correlated`를 확인한다.
6. 이전 run, 실패·미검증 retry와 새 run을 별도로 기록한다. 호출 횟수 제한을 금액 하드캡으로 표현하지 않는다.
7. 다른 mode/transport 조합은 각각 별도 run으로 수행하고 한 조합의 결과를 다른 조합으로 확장하지 않는다.

## Claim boundary

- HTTP 요청은 synthetic target에 전송되지만 local core는 `DirectToolClient`와 in-process `ASGITransport`를 사용한다.
- mock은 로컬 LLM이 아니며 AI 성능 평가 대상이 아니다.
- MCP는 도구 규약이고 권한 제어를 대체하지 않는다.
- 실제 브라우저 UI는 상태 함수/소스 계약 테스트와 구분한다.
- 사용자 제공 VM 결과와 Codex가 직접 실행·검사한 결과를 구분한다.
- API 연결 성공, 후보 생성 결과, verifier 판정과 모델 품질을 서로 구분한다.
- Nmap/Playwright, VM 격리, live OpenAI 결과는 실행 증거가 없으면 완료로 말하지 않는다.
