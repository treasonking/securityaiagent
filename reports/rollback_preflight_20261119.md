# 수동 rollback 회귀 결과 · 2026-11-19

PR #6 head와 리뷰 기준은 모두 `db5715cbb4cf4ee7ca780e62d2c5bd8043349ba6`였다. 임시 checkout, 파일 기반 계획·journal·claim과 가짜 서비스 제어기를 사용해 실제 `VM.rollback`을 호출했다.

수정 전 새 진입점 테스트 7개 중 5개 실패, 2개 통과. claim(기존 상태 두 종류), 실행 중 job, admission 경합에서 원인이 모두 `RECOVERY_REQUIRED`로 바뀌었다. registry 변경은 거절되지 않았다. 정상 rollback과 stop 이후 실패는 기존 기대대로 동작했다.

| 수정 후 조건 | 응답 원인 / 결과 | 배포 journal | stop / launch |
|---|---|---|---:|
| 새 claim | WORKSPACE_NEW_HISTORY_ROLLBACK_REFUSED | HEALTHY 유지 | 0 / 0 |
| 이미 복구 필요 상태에서 새 claim | WORKSPACE_NEW_HISTORY_ROLLBACK_REFUSED | RECOVERY_REQUIRED 유지 | 0 / 0 |
| 실행 중 job | WORKSPACE_RUN_IN_PROGRESS | HEALTHY 유지 | 0 / 0 |
| registry 변경 | RECOVERY_CONFIGURATION_CHANGED | HEALTHY 유지 | 0 / 0 |
| 다른 요청이 admission 보유 | WORKSPACE_BUSY | HEALTHY 유지 | 0 / 0 |
| 서비스 정지 직전 PID 교체 | LISTENER_CHANGED | HEALTHY 유지 | 최종 stop 검사 진입, 신호 0 / 기동 0 |
| 정지 직후 실패 주입 | RECOVERY_REQUIRED | HEALTHY → RECOVERING → RECOVERY_REQUIRED | 1 / 0 |
| 정상 복구 | ROLLED_BACK | HEALTHY → RECOVERING → ROLLED_BACK | 1 / 1 |

사전 거절에서 active 포인터와 journal 바이트, claim/job 내용의 보존을 확인했다. stop 진입 시 별도 submission의 admission 획득을 시도해 같은 fence가 유지되는 것도 확인했다. 전송 테스트에서는 guest CLI 결과와 dispatcher receipt를 host가 같은 sequence로 회수했다. 종료 코드 2, 바깥 원인 `RECEIPT_EXIT_FAILED`, 안쪽 원인 `WORKSPACE_RUN_IN_PROGRESS`였고 pending이 남았다.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_vm_deploy.py tests/test_vm_workspace.py tests/test_vm_deploy_transport.py -p no:cacheprovider --tb=short -o addopts= -q
```

수정 후 관련 회귀 81개 통과. 실제 VM 배포·rollback, 대상 검사, 네트워크 변경 및 UI 시나리오 실행은 이번 검증 범위에서 제외했다.
