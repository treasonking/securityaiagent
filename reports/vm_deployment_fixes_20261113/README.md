# 배포 결과 연결과 IPv6 경로 검사 수정 — 2026-11-13

기준은 `codex/repeatable-vm-deployment`의 `d31ed92c3b28086dc956606dd84c59d304beebf0`다. receipt의 비정상 종료를 이전 성공 결과로 덮는 문제와 IPv6 경로를 명시적으로 수집하지 않은 문제를 수정했다. **전체 pytest 773 passed, 12 warnings, 243.66초**, `npm run build` 성공이다. 실제 VM에서 수행한 검증은 아래와 같으며 재배포 성공을 주장하지 않는다.

## 수정 전 재현과 수정 내용

수정 전 회귀 테스트 3개가 실패했다. 첫 번째는 이전 성공 `apply.json`을 남기고 새 job의 receipt를 exit 23으로 기록했을 때 host CLI가 0을 반환하는 조건이다. 나머지 둘은 Worker/Target 각각 IPv4 기본 경로 없이 IPv6 기본 경로만 주었는데 검사가 거절하지 않는 조건이다. 모두 수정 후 통과했다.

### 작업 결과 연결

- protocol 2의 job, receipt, result에 동일한 sequence/role/action을 넣는다. dispatcher가 자식 CLI에 `--sequence`를 전달한다.
- 작업 결과는 `result-<sequence>.json`, 자식의 실제 종료 코드는 `receipt-<sequence>.json`에 원자적으로 쓴다. `apply.json`/`receipt.json` 같은 최신 표시 별칭은 성공 판단에 사용하지 않는다.
- 정수 exit_code 0, 정확히 boolean true인 result.ok, 세 identity 필드의 일치를 모두 요구한다. 결과 누락·오래된 sequence·역할/작업 불일치·잘못된 JSON·비정상/누락된 종료 코드 중 하나라도 있으면 성공이 아니다. exit 23과 같은 sequence의 ok=true가 동시에 있어도 exit 실패가 우선이다.
- 실패/불확실한 결과와 timeout은 pending을 남기며 새 전송을 차단한다. 나중에 온 receipt가 pending을 자동 해제하지 않는다. `collect --sequence`는 결과만 회수하고 작업을 재전송하지 않는다. 성공으로 확정되지 않은 변경 작업은 운영자의 실제 상태/이력 확인이 필요하다.
- guest는 실행 전에 sequence 소비를 기록한다. 이전 sequence가 다른 job을 거쳐 다시 나타나도 자동 재실행하지 않는다. 중복 dispatcher 실행은 잠금으로 차단한다. host pending 생성도 배타적이다.

### IPv6 경로

`ip -4 -j route show table all`과 `ip -6 -j route show table all`을 각각 호출한다. 정규화된 `routes_ipv4`, `routes_ipv6`를 모두 inventory/plan에 기록한다. Worker/Target은 어느 쪽이든 기본 경로가 있으면 거절한다. IPv6의 일반 경로/metric만 계획 이후 바뀌어도 서비스 중지 전에 `CURRENT_STATE_CHANGED_REPLAN_REQUIRED`로 거절된다. 이 필드는 복구/보존 검사에도 포함된다. Controller는 기존 정책대로 기본 경로 존재 자체를 거절하지 않지만 두 테이블을 모두 기록·비교한다.

이전 단일 `routes` snapshot에 누락된 IPv6 정보를 추정해 채우거나 이전 plan digest를 다시 쓰지 않는다. 새 작업에는 새 계획이 필요하다. protocol 1 ready도 거절하므로 host/dispatcher/guest 도구를 함께 업데이트해야 한다.

## 실제 VM에서 수행한 검증

한국 시각 2026-11-13 작업이며 guest 기록은 UTC 2026-11-12 15시대다. 기존 등록된 세 VM에서 임시 공유의 수정된 도구를 실행했다. 사용자의 기존 서비스 코드/배포 도구를 덮어쓰거나 서비스를 시작·재시작하지 않았다. active release의 commit은 모두 `2120841`이었고, 이번 시작/종료 관찰에서는 세 역할 서비스가 모두 정지 상태였다. 11월 12일 당시 서비스 실행 성공 기록과 이번 관찰 상태를 혼동하지 않는다.

| VM | IPv4 경로 | IPv6 경로 | inspect / stop 연결 | 격리된 자식 실패 | 보호 파일 |
|---|---:|---:|---|---|---:|
| Controller | 13 | 7 | sequence/role/action 일치, exit 0, ok=true | exit 23, 현재 결과 없음, host 실패 판정 | 250 |
| Worker | 9 | 1 | sequence/role/action 일치, exit 0, ok=true | exit 23, 현재 결과 없음, host 실패 판정 | 43 |
| Target | 6 | 1 | sequence/role/action 일치, exit 0, ok=true | exit 23, 현재 결과 없음, host 실패 판정 | 115 |

`inspect`는 실제 새 host sender → 새 dispatcher → 새 guest CLI 경로다. 종료 `stop`은 전달기만 종료하며 애플리케이션 서비스를 종료하는 작업이 아니다. 각 역할의 `history-*.json`에 동일 sequence의 job/receipt/result와 최상위 ok가 함께 있다.

자식 실패 검증은 **실제 VM의 별도 임시 폴더에서 `raise SystemExit(23)`만 실행하는 stub**으로 수행했다. 이전 성공 `apply.json`을 남긴 뒤 동일한 dispatcher `execute_job`을 호출했다. stub은 결과 파일을 쓰지 않았고 receipt는 실제 exit 23이었다. 호스트의 실제 `read_completion`으로 회수된 파일을 평가하니 `ok=false`, `RECEIPT_EXIT_FAILED`, `result_state=missing`, `result=null`이었다. 이전 성공 파일도 그대로 남았다. `apply`라는 job 라벨은 이 격리 재현의 라벨이며 실제 VM 배포 작업을 실행했다는 뜻이 아니다. [Controller 평가](controller/isolated-child-host-evaluation.json), [Worker 평가](worker/isolated-child-host-evaluation.json), [Target 평가](target/isolated-child-host-evaluation.json)를 참고한다.

guest에서 같은 sequence의 두 번째 소비 요청이 거절되는 것도 확인했다. 실제 변경 작업을 timeout 후 재전송하거나 실제 서비스의 실패를 유발하지 않았다.

## 로컬에서만 검증한 조건

집중 회귀 테스트는 기존 배포 테스트와 신규 24개를 합쳐 **56개 통과**했다. 아래 조건은 로컬 테스트의 mock 네트워크/임시 파일 또는 실제 로컬 Python 자식 프로세스로 재현했다.

- 이전 성공 파일이 남은 상태의 결과 기록 전 자식 종료와 host CLI exit 2.
- receipt 비정상/누락/bool 종료 코드, 결과 누락/이전 sequence/역할·작업 불일치/깨진 JSON/ok=false, receipt sequence 불일치.
- 불확실한 작업 뒤 다음 apply/rollback 전송 차단과 pending/job 파일 보존.
- timeout 후 늦은 결과를 `collect`로만 회수하며 기존 job bytes를 바꾸지 않는 조건.
- IPv6 기본 경로만 존재하는 Worker/Target, IPv4 및 IPv6의 기본 경로 표현, 계획 이후 IPv6 일반 경로 metric 변경.
- 자식 실행 시작 실패, 확실한 성공 결과, stop 결과 연결, 지속된 소비 기록의 중복 거절.

실제 VM의 NIC/라우팅/방화벽을 변경하지 않기 위해 **IPv6 기본 경로 추가 및 경로 변경 주입은 로컬에서만** 실행했다. 실제 VM 재배포/rollback, 서비스 장애 주입, 외부 인터넷 도달성 요청, 전원 장애 복구, live OpenAI/UI/function·MCP 시나리오는 이번에 실행하지 않았다.

## 기존 기록과 설정 보존

검증 전후 guest NIC/MAC/IP, IPv4/IPv6 경로, 정규화된 IPv4/IPv6 방화벽 hash, listener 상태가 동일했다. 기존/활성 release의 환경·config·data·run report 및 VM 배포 plans/history 파일 hash를 비교해 보호 파일 408개가 모두 같음을 확인했다. 호스트 VirtualBox NIC와 원래 공유 설정도 같다. 추가한 임시 공유만 unmount 후 제거했다. 비밀값은 guest 내부에서 공개 JSON과 대조했고 일치 0개였다.

`reports/vm_deployment_20261112/`와 `reports/operator_resource_vm_20261107/`는 수정하지 않았다. 그 성공 기록은 당시 코드의 증거로 보존하며, 이번 protocol/IPv6 수정 검증을 소급 적용하지 않는다. 새 증거는 이 폴더에만 추가했다. [summary.json](summary.json)에 실제/로컬 검증 구분과 실행한 도구 source hash가 있다.

재현·운영 방법은 [배포 절차](../../docs/repeatable_vm_deployment.md)를 따른다. 이 수정은 main에 직접 병합하지 않는다.
