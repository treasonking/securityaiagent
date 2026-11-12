# 반복 가능한 실습 VM 배포와 복구

`scripts.vm_deploy`는 등록된 Ubuntu Controller·Worker·Target에서 실행하는 운영자 전용 도구다. 현재 커밋·checkout·환경파일 참조·PID·정책 참조·NIC/route/IPv4·IPv6 방화벽을 기록한 뒤, **완전한 배포 commit과 예상 현재 commit을 명시**해 계획을 만든다. 계획 digest를 별도 확인해야 서비스가 바뀐다. 버전·환경·정책·네트워크·PID가 계획 이후 바뀌면 다시 계획하도록 거절한다. 임의 shell/URL/port/모델 도구를 추가하지 않는다.

[2026-11-12 실제 VM 배포·재배포·복구 결과](../reports/vm_deployment_20261112/README.md)를 참고한다. 기존 operator-resource 기능은 변경하지 않는다.

[2026-11-13 결과 연결·IPv6 검사 수정 검증](../reports/vm_deployment_fixes_20261113/README.md)은 별도 기록이다. 11월 12일의 성공 기록을 수정하거나 이번 수정의 검증 결과로 대체하지 않는다.

## 데이터와 실행 방식

- 기존 `/home/ubuntu/securityaiagent`와 `.env.<role>`를 덮어쓰지 않는다. 현재 활성 release가 있으면 그 경로를 다음 배포의 기준으로 삼는다.
- 신규 release는 `/home/ubuntu/securityaiagent-deployments/releases/<plan-id>`에 detached checkout으로 만든다. 기존 venv를 참조하고, 기존과 `requirements-full.lock`이 다르면 배포를 거절한다. Guest에서 pip/npm/git fetch를 실행하지 않는다.
- 기존 환경파일을 파싱하고 새 역할별 파일을 0600으로 만든다. 값은 보존하되 DB 경로는 새 data 사본으로, Worker registry 경로는 보존한 `runtime-config` 사본으로 연결한다. 기존 Worker의 records/documents/operator 정책을 새 기본 정책으로 바꾸지 않는다. 외부 DB 경로·runtime symlink는 자동 처리하지 않고 거절한다.
- PID/cwd/module을 확인한 서비스만 SIGTERM으로 정상 종료한다. 포트의 다른 프로세스나 종료하지 않는 서비스는 강제로 죽이지 않는다. 새 프로세스는 `common.service_config check/serve`의 고정 역할 명령으로 시작한다. 원래 legacy uvicorn 실행은 복구할 때만 지원한다.
- 정지 후 private Git bundle·workspace archive를 만들고 data와 기존 run report를 복사한다. SQLite online backup, quick_check, 중복 개수까지 포함한 행 비교를 수행한다. private 백업/로그/DB 내용은 보고서로 내보내지 않는다.
- 새 DB는 별도 파일이다. 배포 중 기존 원본 DB·환경·config·report가 그대로인지, 새 DB에 기존 행이 남아 있는지 확인한다. 정상 종료 후 복사하므로 서비스 중단 시간이 있다. zero-downtime 배포가 아니다.
- health는 고정 역할 주소의 `/health` 또는 Controller `/api/health`에서 200과 `status=ok`를 요구한다. 기존 allowlist를 유지하며 loopback source를 사용한다.
- IPv4는 `ip -4 -j route show table all`, IPv6는 `ip -6 -j route show table all`로 각각 수집한다. `routes_ipv4`, `routes_ipv6`를 별도 snapshot 필드로 기록한다. Worker/Target은 어느 테이블이든 기본 경로(`default`, `0.0.0.0/0`, `::/0`)가 있으면 `INTERNET_ISOLATION_UNPROVEN`으로 거절한다. NIC/IP/두 경로 테이블과 정규화한 IPv4·IPv6 방화벽 hash를 비교만 한다. 방화벽/NIC/라우팅 변경 코드는 없다. 내부망 중계 호스트까지 포괄하는 외부 도달성 공격 테스트를 의미하지 않는다.

## 오프라인 패키지와 전달

호스트의 작업 브랜치에서 실행한다. `<commit>`은 배포할 **40자리 SHA**다. 이 커밋은 현재 HEAD의 조상이어야 하고 frontend 소스는 해당 커밋과 같아야 한다. 명령은 호스트에서 frontend를 빌드하고 HEAD Git bundle, 지정 commit manifest, frontend 파일 hash와 운영 도구를 역할별로 준비한다. Git bundle에 포함된 다른 커밋을 배포 버전으로 자동 선택하지 않는다.

```powershell
.\.venv\Scripts\python.exe -m scripts.vm_deploy_host package --exchange verification_tmp/vm_release/exchange --commit <commit>
```

각 `exchange/controller`, `exchange/worker`, `exchange/target`만 해당 VM의 임시 공유로 연결한다. 기존 공유/NIC/방화벽은 바꾸지 않는다. VirtualBox 예:

```powershell
& 'C:/Program Files/Oracle/VirtualBox/VBoxManage.exe' sharedfolder add security-worker --name securityai-deployment --hostpath '<absolute-path>/exchange/worker' --transient
```

사용자가 해당 VM의 터미널에서 로그인·sudo 인증을 한다. 비밀번호를 채팅/명령 인자에 넣지 않는다. 마운트한 뒤 전달기를 유지하면 화면 잠금과 무관하게 승인된 action만 전달할 수 있다.

```bash
sudo -v
sudo mkdir -p /mnt/securityai-deployment
sudo mount -t vboxsf -o uid=1000,gid=1000,umask=077 securityai-deployment /mnt/securityai-deployment
python3 /mnt/securityai-deployment/dispatcher.py --exchange /mnt/securityai-deployment
```

전달기는 shell 문자열을 실행하지 않는다. action과 commit/plan/digest 형식만 받으며, 기존 venv로 `vm_deploy.py`를 호출한다. protocol 2의 job에는 role/action/sequence가 있고 자식에게 `--sequence`를 전달한다. 결과는 `public/result-<sequence>.json`, 실제 자식 종료 코드는 `public/receipt-<sequence>.json`에 원자적으로 기록한다. job·receipt·result의 sequence/role/action이 모두 같고, receipt의 정수 exit_code가 0이며 result.ok가 정확히 true여야 성공이다. 비정상 종료를 결과 파일의 성공으로 덮지 않는다. `apply.json`, `receipt.json` 등 최신 표시용 별칭은 성공 판단에 사용하지 않는다. protocol 1의 ready 파일은 거절하므로 sender/dispatcher/guest 도구를 함께 업데이트한다.

서비스 작업을 transport timeout으로 강제 kill하지 않는다. 결과 누락·이전 sequence·불일치·비정상 종료·timeout이면 `pending.json`을 유지하고 새 전송을 `PREVIOUS_JOB_UNRESOLVED`로 거절한다. receipt가 나중에 도착했다고 자동 재전송하지 않는다. 호스트의 pending 생성은 배타적이며, guest는 실행 전 sequence 소비 기록을 남기고 전달기 중복 실행을 잠금으로 차단한다. 전달기를 재시작하거나 다른 job을 거친 뒤에도 이미 소비한 sequence는 자동 재실행하지 않는다.

늦게 도착한 결과는 **재전송 없이** 회수할 수 있다:

```powershell
.\.venv\Scripts\python.exe -m scripts.vm_deploy_host collect --exchange verification_tmp/vm_release/exchange --role worker --sequence <pending-sequence>
```

collect도 동일한 연결 검사를 적용하며 확실한 성공만 pending을 해제한다. 실패·불확실한 변경 작업은 receipt, 해당 sequence 결과, guest journal 및 실제 listener를 운영자가 확인해야 한다. pending이 남아 있으면 host를 통한 새 status/rollback도 자동 전송하지 않는다. 필요하면 guest 터미널에서 읽기 전용 `vm_deploy.py status --exchange ...`로 확인한다. 확인한 pending/receipt/result를 감사 기록으로 보관하고 운영자가 명시적으로 pending을 해제한 뒤에만 새 복구 작업을 결정한다. pending 파일을 timeout만 보고 삭제하거나 apply를 반복하는 절차는 지원하지 않는다.

## Inspect → plan → 검토 → apply

먼저 세 역할을 모두 inspect해 서로 다른 commit, 정지 상태, 기존 환경/정책 참조를 보고한다. 아래 명령은 worker 예이며 controller/target도 각각 실행한다.

```powershell
.\.venv\Scripts\python.exe -m scripts.vm_deploy_host inspect --exchange verification_tmp/vm_release/exchange --role worker
.\.venv\Scripts\python.exe -m scripts.vm_deploy_host plan --exchange verification_tmp/vm_release/exchange --role worker --commit <deploy-40-sha> --expected <observed-current-40-sha>
```

`VERSION_MISMATCH`는 서비스 중지/새 checkout 준비 전에 반환된다. 확인한 실제 버전과 의도한 버전 변경을 보고한 뒤 올바른 expected로 **새 계획**을 만든다. 자동으로 expected를 실제 값에 맞춰 재시도하지 않는다. 계획의 before/after 경로, environment reference, runtime references, version_change, network/firewall, 데이터 복사 전략을 검토한다. plan은 권한·서명이 아니며 로컬 운영자 확인 기록이다.

```powershell
.\.venv\Scripts\python.exe -m scripts.vm_deploy_host apply --exchange verification_tmp/vm_release/exchange --role worker --plan <32-character-plan-id> --confirm <64-character-reviewed-digest>
```

일반 순서는 Target → Worker → Controller다. 필요한 역할만 선택할 수 있다. 세 역할은 별도 트랜잭션이며 전체 fleet의 원자적 전환을 보장하지 않는다. 부분 실패 시 해당 역할은 자동 복구하고, 이미 성공한 다른 역할의 rollback은 명시적으로 실행한다. 계획마다 역할이 고정돼 있다.

상태는 `STOPPING → STOPPED → BACKED_UP → STARTING → HEALTHY`로 영속 기록한다. 같은 성공 계획을 다시 apply하면 현재 commit·환경·정책·health·보존을 확인하고 `ALREADY_HEALTHY`를 반환하며 재시작하지 않는다. 실패·복구한 계획을 재사용하지 않고 새 plan을 만든다. 같은 commit을 새 plan으로 다시 배포하면 실행 중인 서비스를 정상 재시작하는 경로가 된다.

## 실패 복구와 명시적 rollback

IPv6가 별도 필드에 포함되면서 기존 단일 `routes` snapshot 계획과 새 inventory의 구조가 달라졌다. 이전 plan/digest/성공 이력을 자동 수정하거나 누락된 IPv6 정보로 검사를 완화하지 않는다. 새 배포는 두 경로 테이블을 기록한 새 계획으로 진행한다. 이전 계획을 이용한 복구가 필요하면 운영자가 기존 이력과 현재 IPv4/IPv6 상태를 별도로 검토해야 하며, 이 수정은 이전 계획의 자동 변환을 제공하지 않는다.

배포 중 backup/start/health/보존 검사가 실패하면 `RECOVERING`으로 전환해 새 서비스만 정상 종료하고 원래 checkout/환경/실행 방법으로 돌아간다. 원래 실행 중이었다면 다시 시작해 health를 확인하고, 원래 정지 상태였다면 정지 상태로 복구한다. 성공한 자동 복구는 `ROLLED_BACK_AFTER_FAILURE`, 복구까지 실패하면 `RECOVERY_REQUIRED`로 남고 성공으로 보고하지 않는다. 프로세스 강제 종료·호스트 전원 손실로 중단된 경우 자동 재개하지 않는다. journal을 확인하고 아래 명령으로 복구한다.

```powershell
.\.venv\Scripts\python.exe -m scripts.vm_deploy_host status --exchange verification_tmp/vm_release/exchange --role worker
.\.venv\Scripts\python.exe -m scripts.vm_deploy_host rollback --exchange verification_tmp/vm_release/exchange --role worker --plan <plan-id> --confirm <reviewed-digest>
```

복구 대상의 commit·환경·config·네트워크가 달라졌거나 더 새로운 배포가 활성 상태면 조용히 이전 코드로 덮지 않는다. 자동 DB 덮어쓰기나 schema downgrade는 하지 않는다. **새 release에서 배포 후 발생한 쓰기는 그 release/data에 보존되며, rollback한 이전 DB에 자동 합쳐지지 않는다.** 업무 쓰기가 발생했다면 복구 후 데이터 전환/병합은 별도 검토가 필요하다. 이번 실습은 health만 호출했으며 업무 쓰기/마이그레이션 검증이 아니다.

실행 journal·plan·백업·새 데이터를 남긴다. 결과 회수 후 `stop`을 전달하고 임시 마운트/VirtualBox mapping을 제거한다. 각 VM의 원래 공유는 유지한다.

```powershell
.\.venv\Scripts\python.exe -m scripts.vm_deploy_host stop --exchange verification_tmp/vm_release/exchange --role worker
```

보고서는 `public/result-*.json`, `public/receipt-*.json`, `public/history-*.json` 등 검토한 결과만 수집한다. 이전 protocol의 `public/history/` 기록은 그대로 보존한다. `release.bundle`, populated 환경파일, private 로그/archive/DB를 커밋하지 않는다. 현재 도구는 서비스 시작 방식을 systemd로 바꾸거나 부팅 자동 실행을 설치하지 않는다. 재부팅 뒤 active release 참조를 읽어 새 계획을 만들 수 있지만 전원 장애 자동 재기동 관리자는 아니다.
