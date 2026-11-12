# 반복 가능한 VM 배포·복구 실제 결과 — 2026-11-12

세 Ubuntu VM에 명시한 커밋 **`2120841ae8dcf341352bb03b1e076d0367980363`**을 오프라인으로 배포했다. 각 VM에서 첫 배포, 실행 중 서비스의 두 번째 배포, 직전 release로 rollback, 같은 성공 계획 재적용을 수행했다. 6번의 배포와 3번의 rollback 모두 health 200이었다. 최종 상태는 세 역할 모두 첫 번째 `2120841` release 실행 중이다. 기존 checkout을 최신 코드로 덮어쓰지 않았다.

구현 기준 브랜치는 `codex/operator-resource-vm-verification`의 `2120841`, 새 작업 브랜치는 `codex/repeatable-vm-deployment`다. 배포 대상 서비스 코드와 새 배포 도구 버전은 구분한다. 실제 서비스는 위 명시 커밋이며, VM에 보관한 최종 도구의 SHA-256은 각 `redaction.json`과 [summary.json](summary.json)에 있다.

## 먼저 확인한 상태

| 역할 | 기존 커밋 | 기존 checkout / 환경 참조 | 초기 서비스 | 기존 실행 방식 |
|---|---|---|---|---|
| Controller | e54d776 | `/home/ubuntu/securityaiagent` / `.env.controller` | 정지 | legacy uvicorn factory |
| Worker | ef25892 | `/home/ubuntu/securityaiagent` / `.env.worker` | 정지 | common.service_config |
| Target | ef25892 | `/home/ubuntu/securityaiagent` / `.env.target` | 정지 | common.service_config |

버전 차이를 사용자에게 보고했다. Controller의 expected를 의도적으로 `2120841`로 지정한 plan은 실제 `e54d776`과 달라 **`VERSION_MISMATCH`**로 중단됐다. 이 실패는 [Controller job 기록](controller/history/7fc91dbf92f94cf79efc1b551969af31.json)에 남아 있다. 서비스 중지/배포 준비를 하지 않았고, 확인한 실제 현재 SHA를 명시한 새 계획으로 진행했다. 이후 각 역할의 실제 환경파일 참조, 설정 키 이름(값 제외), runtime 경로, PID/cwd/module, NIC/route/firewall을 계획에 기록했다.

Worker의 기존 정책은 `config/targets.records.json`, Target의 기존 DB 참조는 `data/vm-target-live-vulnerable.sqlite3`였다. 기본 documents/operator 정책이나 테스트 DB로 조용히 바꾸지 않았다. Worker registry는 신규 release의 `runtime-config` 사본으로, DB 참조는 신규 release의 `data` 사본으로 연결했다. 원래 파일과 원래 DB는 유지했다.

## 실제 VM에서 수행한 항목

| 역할 | 첫 배포 | 실행 중 재배포 | 직전 release 복구 | 재적용 | 보존 DB |
|---|---|---|---|---|---:|
| Controller | HEALTHY / 200 | HEALTHY / 200 | ROLLED_BACK / 200 | ALREADY_HEALTHY | 2 |
| Worker | HEALTHY / 200 | HEALTHY / 200 | ROLLED_BACK / 200 | ALREADY_HEALTHY | 1 |
| Target | HEALTHY / 200 | HEALTHY / 200 | ROLLED_BACK / 200 | ALREADY_HEALTHY | 5 |

첫 배포는 원래 정지한 서비스에 새 release를 시작한 것이다. 두 번째 배포에서 실제 실행 중 PID/cwd/module을 확인하고 SIGTERM으로 종료한 뒤 새 release를 시작했으므로 **재시작 경로도 실제 VM에서 실행했다**. 복구는 두 번째 release를 정상 종료하고 첫 번째 release를 다시 실행했다. 같은 첫 계획의 재적용은 재시작 없이 health/보존 검사를 수행했다.

계획과 실제 job은 역할별 `history`에 있다. 기록에는 expected/deploy SHA, reviewed digest, release 경로, 상태 전이, health, 보존 결과가 포함된다. VM별 시간 차이가 있으므로 cross-VM timestamp만으로 엄격한 전역 순서를 추론하지 않는다. 이번 실행은 각 역할의 별도 배포 트랜잭션이며 fleet 전체 atomic deployment 검증이 아니다.

최종 실행 경로:

- Controller: `/home/ubuntu/securityaiagent-deployments/releases/2b1c96b347234d57a4a3acdb4f12af10`
- Worker: `/home/ubuntu/securityaiagent-deployments/releases/3d88cb99dc5e48b3aefed13a5fda46e6`
- Target: `/home/ubuntu/securityaiagent-deployments/releases/7c6a5729e910425cb28a36653d47e54a`

각 경로의 `.env.<role>`과 `data`를 사용한다. 현재 상태는 [Controller](controller/status.json), [Worker](worker/status.json), [Target](target/status.json)에서 확인할 수 있다. 원래 `/home/ubuntu/securityaiagent` 및 원래 환경파일/DB는 남아 있으며, first plan으로 rollback하면 **원래 정지 상태**로 돌아간다.

각 VM의 `/home/ubuntu/securityaiagent-deployments`에 plans, history, private backups, release 데이터, 최종 `tools/vm_deploy.py`와 `tools/dispatcher.py`, 정제 감사 기록을 남겼다. 전송용 dispatcher는 종료하고, 임시 공유는 guest에서 unmount한 뒤 VirtualBox transient mapping을 제거했다. 원래 `securityai-update` 공유는 유지했다.

## 보존과 격리

기존 환경파일·config·run report hash와 SQLite 행을 비교해 원본이 동일함을 확인했다. SQLite quick_check와 새 사본의 기존 행 보존 검사를 수행했고, 중복 행의 개수도 비교한다. 총 8개 DB를 보존했다. 백업은 VM 내부 private 디렉터리에만 저장했으며 원본 DB/환경/로그를 Git에 올리지 않았다.

Worker·Target은 VirtualBox 내부망 NIC만 갖고 있으며 기본 route가 없음을 확인했다. 호스트 NIC 설정, guest NIC/MAC/IP/route, 정규화한 IPv4·IPv6 방화벽 hash가 전후 같다. 코드 업데이트는 호스트가 만든 Git bundle/이미 빌드한 frontend를 임시 공유로 전달했다. Guest 인터넷 연결, DNS, 방화벽, NIC 변경이나 pip/npm 설치는 수행하지 않았다. 외부 사이트로 인터넷 차단을 시험하는 요청도 보내지 않았다.

새 서비스는 **DB 사본**을 사용한다. rollback은 이전 release의 DB를 사용하며 새 release의 데이터는 삭제하지 않는다. 배포 후 쓰기를 이전 DB에 자동 병합하거나 DB 스키마를 자동 downgrade하지 않는다. 이번에는 배포 health만 요청했고 업무 쓰기/마이그레이션은 검증하지 않았다.

공개 JSON만 선별해 회수했다. 각 VM 내부에서 원래/새 역할 환경의 비밀값과 전체 공개 job payload를 비교했다. Controller 5개, Worker 4개, Target 3개 값에 대해 일치 0개였다. 비밀번호·토큰·API key·raw proof 값은 보고서에 없다. `redaction.json`에는 검사 개수와 최종 tool hash만 남겼다.

## 로컬 검증과 실제로 실행하지 않은 범위

배포 상태 전이의 단위 테스트는 backup/health/보존 실패에서 원래 실행 중/정지 상태 복구, 복구 실패의 `RECOVERY_REQUIRED` 기록, 계획 digest 변조·환경/버전/네트워크/PID drift 거절, 이전 계획 재사용 거절, 새 배포를 덮는 rollback 거절, 중복 DB 행 손실 탐지, 잘못된 host job 거절을 검증한다. 이 장애 주입은 **로컬 mock backend**에서 실행했으며 실제 VM 장애 주입으로 표시하지 않는다.

최종 전체 pytest는 **749 passed, 12 warnings, 229.70초**, frontend build는 성공했다. [summary.json](summary.json)의 `local_only`에도 기록했다. 기존 애플리케이션 회귀도 포함한 결과이며 VM 배포 성공의 대체 증거가 아니다. 초기 전체 검증은 743개, 복구 source 검사 추가 후 745개가 통과했고, 최종 749개는 host 입력 검사까지 포함한다. 경고는 기존 Pydantic/MCP deprecation 및 pytest cache 쓰기 경고이며 실패가 아니다.

실제 VM에서 검증하지 않은 것은 자동 health 실패 주입, 전원 상실/강제 종료 후 복구, DB schema migration/쓰기 병합, legacy 실행 중 Controller로의 rollback, 부팅 자동 실행, function/MCP 시나리오 재실행, UI/browser, live OpenAI다. 이 PR은 기존 scenario 기능을 수정하지 않는다. 이전 11월 7일의 operator-resource 네 조합 결과를 이번 배포 검증으로 재사용하지 않았다.

VM 작업 전달에는 이 세션의 고정 경로 bootstrap dispatcher를 사용했고, 배포 엔진과 host sender는 새 구현을 실제 실행했다. 재사용 가능한 `vm_deploy_dispatcher.py`의 exchange 인자와 재시작 후 sequence 중복 방지 경로는 이번 VM에서 따로 재실행하지 않았다. 최종 범용 dispatcher 파일은 VM에 보관했다.

## 진행 중 발생한 문제와 처리

1. Worker/Target의 sudo 후속 명령은 인증 만료로 중단됐다. 기존 서비스 변경 전에 사용자 인증을 갱신했고 상태 수집을 재실행했다.
2. 확인된 현재 버전과 다른 expected 입력은 `VERSION_MISMATCH`로 거절됐다. 의도한 부정 검증이며 배포 실패로 숨기지 않았다.
3. 최종 감사 기록 회수 시 VirtualBox 공유의 호스트 생성 `public/history` 하위 폴더 접근이 거절됐다. 단일 JSON payload로 전달해 guest 내부에서 전체 비밀값 검사를 완료하고 기록을 보관했다. 앱/DB 동작과는 무관하며 임시 공유 정리까지 성공했다.
4. 구현 중 복구 대상 코드/환경 drift 검사와 host 입력 형식 검사를 보강했다. 최종 복구 source 검사는 실제 VM rollback에서, host의 잘못된 입력 거절은 로컬 테스트에서 확인했다. 실제 서비스 배포 커밋은 계속 `2120841`이다.

재현 명령과 복구 제한은 [운영 절차](../../docs/repeatable_vm_deployment.md)를 따른다. main은 `17d72b8`로 기준 브랜치보다 뒤에 있으므로 main 대상 PR에는 선행 25개 커밋의 기능/증거도 포함된다. 이번 추가 구현 범위는 `2120841..codex/repeatable-vm-deployment`이며 main을 직접 병합하지 않는다.
