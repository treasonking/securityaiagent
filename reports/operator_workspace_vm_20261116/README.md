# 운영자 워크스페이스 실습 VM 적용

2026-11-16 KST에 기존 세 VM의 활성 커밋 `2120841ae8dcf341352bb03b1e076d0367980363`에서 `97d10e25298261775bc4423dab1d6226ed22a156`을 별도 release에 적용했다. 초기 서비스는 모두 정지 상태였고 기존 Controller에는 workspace 설정이 없었다. 기존 환경에서 인증 설정을 보존하고 새 프로필만 파생 환경에 추가했다.

| 실제 브라우저에서 실행한 조합 | 준비 상태/preview 중 Target 수신 증가 | 실행 중 Target 수신 증가 | 도구 / 증거 | 판정 및 저장 증거 재판정 |
|---|---:|---:|---:|---|
| cookie · function · 취약 | 0 | 11 | 12 / 11 | VULNERABLE 일치 |
| cookie · MCP · 수정 | 0 | 11 | 12 / 11 | BLOCKED_BY_ACCESS_CONTROL 일치 |

Target은 승인된 내부 HTTP origin을 사용했다. 각 계측 구간에서 동일 Target 프로세스의 수신 계수가 2 → 2 → 13으로 변했다. 초기 2회는 계측 시작 전 수신이다. 기대 판정과 Target 수신 계수는 verifier 입력에 사용하지 않았다. [두 run의 ID, digest, 정책 snapshot, 실제 계수와 재판정](runs.json)

Target → Worker → Controller 순으로 배포했고 수정 모드 전환 때 Target에만 별도 계획을 적용했다. 네 번의 apply가 모두 health 200을 반환했다. 세 역할의 원본 환경·설정·보고서와 DB 행을 배포 시점에 대조했다. 최초 배포에서 대조한 DB 수는 Controller 2, Worker 1, Target 5였다. NIC, 경로, 방화벽 비교도 통과했다. Worker·Target에는 IPv4/IPv6 기본 경로가 없었다. [역할별 경로·커밋·digest·보존 결과](deployment.json)

실제 UI에서 로그인, 등록 프로필, readiness, preview, 계획 확인 후 제출, 두 결과 표시를 확인했다. Controller 정상 재시작 후 health 200, 브라우저 새로고침 및 기존 상태 조회에서 두 제출·결과가 복원됐다. 재시작 전후에 같은 두 계획을 인증·CSRF를 거쳐 제출했을 때 모두 HTTP 409 `PLAN_ALREADY_SUBMITTED`였다. 두 run의 Markdown/JSON 다운로드 API가 HTTP 200과 attachment를 반환했다. 네 파일의 바이트가 재시작 전후 동일했고 JSON의 증거가 저장된 run의 증거와 일치했다. 브라우저 도구의 다운로드 완료 알림은 시간 초과되어 사용자 다운로드 폴더 저장은 확인하지 못했다.

### 수행 명령

호스트에서 `python -m scripts.vm_deploy_host`의 `prepare-workspace`, `package --commit <배포 SHA>`, 역할별 `status`, `plan --commit <배포 SHA> --expected <관측 SHA>`, `apply --plan <ID> --confirm <digest>`를 실행했다. 역할과 exchange는 고정된 실습 VM 경로를 지정했다. 두 번째 Target 계획 전에 `prepare-fixed`를 실행했다. Target 수신은 `counter`, Controller 정상 재시작은 `service-restart --expected <배포 SHA>`로 확인했다. 실제 ID와 SHA는 deployment.json에 있다. 번들의 SHA-256은 `e17959073baf7547022cc964e23c3c8b0db0fa0c8cd12f1e1f386a954453250e`다.

### 실패와 검증 경계

- 11월 16일 VM 재부팅으로 임시 공유가 해제됐다. 공유 복원 후 기존 sequence를 회수했다. 세 초기 plan이 exit 2로 실패했으며 새 release를 적용한 서비스는 없었다. guest에서 bundle은 읽혔지만 새 setup 파일을 열 때 errno 71이 발생했다. 호스트의 새 setup 디렉터리에서 VirtualBox 실행 사용자의 읽기 권한이 빠져 있었다. 실패 receipt와 journal을 확인하고 해당 권한만 보완한 뒤 새 plan 세 개를 발급했다.
- 실제 VM에서는 신규 프로필 배포와 두 실행 후 정상 재시작까지 검증했다. 기존 workspace 이력이 있는 release의 교체, 이력이 바뀐 release의 rollback 거절, 링크 및 경로 변경 거절은 로컬 회귀에서 검증했다. 실 VM rollback과 긴 증거 펼침 상태의 화면 배치는 미검증이다.
- 로컬에서 `.\.venv\Scripts\python.exe -m pytest`가 937 passed, 41 warnings로 완료됐다. 최초 중단된 실행은 제외했다. frontend의 `npm test`는 16 passed, `npm run build`는 성공했다.
- 11월 19일 재부팅 후 최초 Controller 연결은 거절됐다. 이후 같은 UI 주소의 health가 `ok`로 복구됐고 인증된 profiles에서 `vm-prepared-resources`가 준비 상태였다. 기존 두 run의 저장 증거를 다시 조회하고 Markdown·JSON을 다운로드해 11월 16일 보관한 네 파일과 바이트 단위로 일치함을 확인했다. 서비스 시작 원인과 부팅 자동 시작은 확인하지 않았다.
