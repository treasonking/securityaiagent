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
set -a
source .env.target
set +a
.venv/bin/python -m uvicorn target.app:app --env-file .env.target --host 10.78.0.30 --port 8080
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

셸의 기존 환경변수는 dotenv보다 우선할 수 있으므로 provider나 mode를 바꿀 때 현재 프로세스 환경을 확인한다. 재시작 후 UI에서 마지막 결과가 복원되는지는 controller의 동일 `DATABASE_PATH`와 설정을 사용했을 때만 유효한 관찰이다.

## 2026-10-14 reported VM example

사용자가 제공한 기록에서는 `mock` provider로 vulnerable/fixed × function/MCP 네 조합을 각 1회 실행했고 모두 target-local 5/5 대조 후 정제 결과를 수동 import했다. 네 run ID와 digest, 확보 상태는 [`current_verification.md`](../reports/current_verification.md)와 [`evidence_index.md`](../reports/evidence_index.md)에 기록한다. 이 문서 수정은 Codex가 VM에서 해당 시나리오를 재실행했다는 뜻이 아니다.

## Claim boundary

- HTTP 요청은 synthetic target에 전송되지만 local core는 `DirectToolClient`와 in-process `ASGITransport`를 사용한다.
- mock은 로컬 LLM이 아니며 AI 성능 평가 대상이 아니다.
- MCP는 도구 규약이고 권한 제어를 대체하지 않는다.
- 실제 브라우저 UI는 상태 함수/소스 계약 테스트와 구분한다.
- 사용자 제공 VM 결과와 Codex가 직접 실행·검사한 결과를 구분한다.
- Nmap/Playwright, VM 격리, live OpenAI 결과는 실행 증거가 없으면 완료로 말하지 않는다.
