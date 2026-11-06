# Operator resource: 실제 VM 검증 절차

기준은 `b574ba4`이며 새 `operator-target` launcher만 추가한다. Controller의 `controller.operator_execution` CLI, Worker의 operator-resource 계약 및 verifier 판정은 기준 구현을 유지한다. 기존 UI는 사용하지 않는다. 독립 API는 `/session`, `/me`, `/tickets/{resource_id}`와 health를 제공하며 cookie 인증으로 시작한다. 기존 TargetStore/DB/canary helper를 사용하지 않는다.

## 전용 서비스 설정

`.env.operator-target.example`을 **새 checkout의 새 파일**로 복사하고 두 계정의 새 비밀번호와 서로 다른 새 proof를 채운다. 각 비밀은 `secrets.token_urlsafe(32)` 등으로 새로 생성한다. 값은 Git, 공개 출력, controller 파일에 넣지 않는다. 동일한 테스트 자격증명/proof를 전용 Worker 환경에 안전하게 전달한다. Target 파일에는 Worker token/OpenAI/UI 비밀을 넣지 않는다. Controller와 Worker의 전용 파일에만 동일한 새 Worker token을 넣는다.

```bash
# 신규 checkout에서만 실행. 기존 .env.target/.env.worker를 덮어쓰지 않는다.
.venv/bin/python -m common.service_config check operator-target --env-file .env.operator-target.vulnerable
.venv/bin/python -m common.service_config check worker --env-file .env.worker.operator
```

Target의 모드는 별도 파일의 `OPERATOR_TARGET_MODE=vulnerable` 또는 `fixed`다. 두 모드 파일의 계정/proof는 같아야 한다. Worker registry는 별도 checkout의 `config/targets.operator.json`, target origin은 `http://10.78.0.30:8080`, Worker endpoint는 `http://10.77.0.20:9000`이다. 자유 host/port/URL 인자는 지원하지 않는다. 실효 한도는 HTTP 11/도구 12, 기본 초당 2회다.

## 보존·전환

1. 세 VM의 전원, HEAD/수정 상태, listener PID/cwd/module 및 서비스 실행 방식을 먼저 확인한다. 기존 환경파일의 **값을 출력하지 않고** 설정 검사 결과만 기록한다.
2. 각 VM 내부 사용자 전용 0700 디렉터리에 기존 Git bundle, 코드/환경/데이터 archive, SQLite online backup을 저장한다. 환경/config/기존 report/plan 파일의 해시, SQLite quick_check와 기존 행, NIC/MAC/IP 및 정규화된 firewall 상태를 비교 기준으로 보존한다. 원본 DB/로그를 verifier 입력이나 공유폴더로 보내지 않는다.
3. 새 bundle을 별도 checkout에 배치하고 기준 커밋의 후손인지 확인한다. 의존성이 같다면 기존 venv를 참조하되 설치·수정하지 않는다. 새 환경파일은 0600으로 둔다. 기존 checkout을 변경하거나 기존 DB를 reset하지 않는다.
4. 같은 포트의 기존 listener가 승인된 저장소의 해당 uvicorn module임을 확인한 뒤 SIGTERM으로 정상 종료한다. 다른 프로세스거나 소유자가 불명확하면 중단하고 조사한다. 강제 kill이나 포트 일괄 종료를 하지 않는다.
5. 새 Target을 먼저, Worker를 다음에 실행한다. Controller 서버/UI는 전환하지 않는다.

```bash
.venv/bin/python -m common.service_config serve operator-target --env-file .env.operator-target.vulnerable
.venv/bin/python -m common.service_config serve worker --env-file .env.worker.operator
```

수정 모드 전환은 새 테스트 Target 프로세스만 정상 종료한 뒤 같은 checkout에서 fixed 환경파일로 다시 기동한다. Worker 정책과 자격증명/proof가 같으므로 모드 전환 자체는 Worker 정책 변경이 아니다. 모드는 verifier에 전달하지 않는다.

## 네 번의 별도 실행

취약/function, 취약/MCP, 수정/function, 수정/MCP 각각 새 importer 출력과 preview를 만든다. [기존 preview/run 가이드](operator_resource_runbook.md)의 명령에서 전용 `.env.controller.operator`를 선택한다. 실제 plan을 읽어 대상, 계정/principal/리소스, 순서, 인증, provider/transport, 실효 한도, snapshot 및 300초 TTL을 검토한 다음 **별도 명령에 그 digest를 명시**하여 run한다. Codex의 검토는 `--approved-by codex`로 기록한다. 계획을 읽지 않고 자동으로 digest를 연결하는 방식으로 대체하지 않는다.

Target은 checkout 내부 `verification_tmp/operator_target_counter.json`에 요청 수와 process identity/시각만 기록한다. 요청 본문·헤더·계정·proof·응답·모드를 기록하지 않는다. 이 파일은 운영 계수이며 verifier 입력이 아니다. 각 preview 직전/직후 및 run 직후에 이 수치를 스냅샷으로 보존한다. 구간 사이에 health 등 다른 요청을 보내지 않고 같은 PID/시작 시각인지 확인한다.

- preview delta = 0; run delta = 11. 실제 API 수신 수이며 TCP 패킷 수가 아니다.
- Worker 실제 사용량 = HTTP 11/도구 12; evidence = 11.
- plan/issued/claim/link/report의 digest, 실제 Worker 정책 및 실행 ID 연결 일치.
- 저장 evidence/verification_contract/report만으로 `python -m verifier.operator --run-dir ...` 재판정 일치.
- 취약은 `VULNERABLE`, 수정은 `BLOCKED_BY_ACCESS_CONTROL`. 범위 거절/실패/불완전 제어는 `INCONCLUSIVE`로 남기고 실패 기록을 삭제하지 않는다.

## 복구와 회수

새 Target·Worker만 SIGTERM으로 종료하고 원래 checkout에서 원래 `.env.target`, `.env.worker`를 사용하는 확인된 서비스 명령으로 복구한다. Controller는 원래 서비스를 유지한다. 세 서비스 health, 기존 코드 HEAD, 환경/config/기존 결과 파일 해시, SQLite quick_check/기존 행, NIC/MAC/IP/firewall을 다시 비교한다. 새 checkout/환경/plan 이력/실행 증거는 보존한다.

추가한 임시 공유는 결과 회수 후 마운트 해제하고 VirtualBox transient mapping을 제거한다. 원래 공유와 NIC/MAC/firewall은 유지한다. 비밀 파일과 원본 DB/로그는 공개 산출물에서 제외하고, plan·정제 evidence·report·실제 계수·복구 검사만 Git에 기록한다. 원본 byte SHA-256을 위해 증거 폴더의 Git 줄바꿈 변환을 금지한다.

VM이 부팅 중 정지하여 정상 종료에 응답하지 않는 경우는 앱 검증 실패와 구분한다. 현재 상태 보존과 복구 조치·사용자 승인을 기록하고, VM 실행에 성공하기 전 로컬 테스트 결과를 VM 성공으로 표시하지 않는다. VM별 실제 결과와 미검증 항목은 별도 실행 보고서에 남긴다.
