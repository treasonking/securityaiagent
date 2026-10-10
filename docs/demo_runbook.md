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

## VM sequence

1. [`network_setup.md`](network_setup.md)에 따라 세 VM의 snapshot, NIC, route, forwarding, firewall 정책과 counters를 저장한다.
2. [`environment_loading.md`](environment_loading.md)에 따라 역할별 `.env.target`, `.env.worker`, `.env.controller`를 각 VM에만 만든다. 비밀 파일은 커밋하지 않는다.
3. target에서 환경을 로드하고 `python -m target.cli reset`을 실행한 뒤 `TARGET_MODE=vulnerable`로 시작한다.
4. worker와 controller를 역할별 `--env-file`로 시작한다. controller는 `--workers 1`을 유지한다.
5. controller의 별도 shell에도 `.env.controller`를 로드한 뒤 `python -m controller.cli doctor` 결과와 종료 코드를 저장한다. Uvicorn의 `--env-file`은 다른 shell에 적용되지 않는다.
6. UI에서 `APP_ACCESS_TOKEN`으로 로그인한 뒤 `lab-web`, `access-control`, `mock`, `function`을 실행한다.
7. 완료 후 evidence 5개, 결과 메시지, 새로고침 복원, 대화 전환의 stale-response 차단, 취소 후 다음 run 실행을 직접 확인한다.
8. 같은 mode에서 `mock` + `MCP`를 별도 실행한다.
9. target-local DB로 두 run을 reset 전에 각각 오프라인 평가한다. controller로 target DB를 복사하거나 평가를 위해 직통 경로를 열지 않는다.
10. target을 종료하고 mode를 `fixed`로 바꾼 뒤 환경 로드 → reset → 재시작 순서로 같은 function/MCP 절차를 반복한다.

| Mode | Transport | Online completion | Required offline verdict |
|---|---|---|---|
| vulnerable | function | completed; socket-separated run은 correlation 전 `INCONCLUSIVE`일 수 있음 | `VULNERABLE`, 5/5 |
| vulnerable | MCP | completed; socket-separated run은 correlation 전 `INCONCLUSIVE`일 수 있음 | `VULNERABLE`, 5/5 |
| fixed | function | completed; socket-separated run은 correlation 전 `INCONCLUSIVE`일 수 있음 | `BLOCKED_BY_ACCESS_CONTROL`, 5/5 |
| fixed | MCP | completed; socket-separated run은 correlation 전 `INCONCLUSIVE`일 수 있음 | `BLOCKED_BY_ACCESS_CONTROL`, 5/5 |

CLI run은 controller DB/UI에 등록되지 않는다. 정상 완료여도 correlation 대기 때문에 verdict가 `INCONCLUSIVE`이면 종료 코드 1을 반환한다. UI offline import 시험에는 UI에서 생성한 run과 정제된 `offline_verification.json`만 사용한다.

## Claim boundary

- HTTP 요청은 synthetic target에 전송되지만 local core는 `DirectToolClient`와 in-process `ASGITransport`를 사용한다.
- mock은 로컬 LLM이 아니며 AI 성능 평가 대상이 아니다.
- MCP는 도구 규약이고 권한 제어를 대체하지 않는다.
- 실제 브라우저 UI는 상태 함수/소스 계약 테스트와 구분한다.
- Nmap/Playwright, VM 격리, live OpenAI 결과는 실행 증거가 없으면 완료로 말하지 않는다.
