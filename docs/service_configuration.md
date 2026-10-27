# 서비스별 API·인증 설정

2026-10-27 작업은 기존 scope-policy 최신 `f21c8e5`에서 시작한 `codex/service-auth-config` 브랜치에 있다. controller·worker·target의 운영자 환경 파일을 분리하고, 선택한 파일만 검증·전달하는 실행 경로를 추가했다. API endpoint나 인증 프로토콜을 새로 만들거나 외부 사이트용 어댑터를 추가한 작업은 아니다.

## 설정 소유권

| 서비스 | 예제 → 해당 VM의 로컬 파일 | 보관하는 설정·인증값 |
|---|---|---|
| controller | `.env.controller.example` → `.env.controller` | worker function/MCP 주소와 WORKER_TOKEN, UI 접근 토큰/세션 서명키, offline import 토큰, 선택적 OpenAI 키·모델, controller DB·허용 목록 |
| worker | `.env.worker.example` → `.env.worker` | 수신 WORKER_TOKEN, 실습 계정 비밀번호, scope registry 경로/origin 동등성 검사, 전역 한도·수신 허용 목록 |
| target | `.env.target.example` → `.env.target` | 합성 계정 비밀번호, target DB 경로, TARGET_MODE |

`WORKER_TOKEN`은 controller→worker의 동일한 인증 경계를 공유하므로 두 서비스에 같은 값이 필요하다. `LAB_*_PASSWORD`는 worker 로그인값과 target 계정 비밀번호가 일치해야 한다. 이 공유를 UI 접근 토큰, 세션 서명키, offline import 토큰, OpenAI 키와 혼동하지 않는다. 새 검사기는 controller의 서로 다른 인증 경계에 같은 값을 재사용하면 거절한다. 비밀번호·토큰은 예제에 공란이며 로컬에서 채운다. OpenAI 키는 controller에만 둔다.

`.env.example`은 서비스별 예제를 가리키는 안내로 바꿨다. 기존 실제 `.env.*`와 DB는 수정하지 않았다. 정확한 세 예제만 Git 추적 예외이며 실제 환경 파일은 계속 ignore한다. 환경 변수 이름·API 경로·Bearer/session 인증 방식은 유지한다.

## 검사와 실행

아래 명령은 **운영자가 다음 배포 때 실행할 명령**이다. 이번 작업에서 VM 서비스를 시작하거나 변경하지 않았다. 각 VM에서는 자신의 예제 파일만 복사하고 필요한 값을 채운다. Windows에서는 `Copy-Item .env.worker.example .env.worker`와 같은 방식으로 복사할 수 있지만 기존 파일이 있다면 덮어쓰지 말고 필요한 키만 비교·반영한다.

Windows 저장소 루트:

```powershell
.\.venv\Scripts\python.exe -m common.service_config check controller --env-file .env.controller
.\.venv\Scripts\python.exe -m common.service_config serve controller --env-file .env.controller
```

worker/target VM에서는 `controller`를 각각 `worker`/`target`으로, 파일명을 해당 서비스로 바꾼다. Ubuntu:

```bash
.venv/bin/python -m common.service_config check worker --env-file .env.worker
.venv/bin/python -m common.service_config serve worker --env-file .env.worker
```

`--env-file` 생략 시 저장소 루트의 `.env.<service>`를 사용한다. 지정 경로는 운영자 CLI에서만 입력한다. 채팅·모델·UI에는 파일 선택 기능을 추가하지 않았다. `check`는 API/모델/target에 요청하지 않고 애플리케이션이나 DB를 초기화하지 않는다. 성공 exit 0은 설정 이름·설정된 비밀 키의 **이름만** 출력한다. worker는 기존 scope 해석기로 계산한 profile/revision/hash/실효 한도도 출력한다. 인증 성공, 서버 접근 가능, VM 복원 완료를 의미하지 않는다.

오류 exit 2는 `SERVICE_CONFIG_INVALID`와 값 없는 진단을 출력한다. 다른 서비스의 키, unknown/중복 키, 파싱 오류, `${...}` 환경 치환, 비어 있는 필수 비밀값은 거절한다. worker token 최소 16자, UI 접근 토큰 최소 16자, 세션 서명키 최소 24자다. 새 launcher에서는 target/worker의 세 계정 비밀번호도 명시적으로 필요하며 기본 실습 비밀번호로 자동 대체하지 않는다. 단일 줄 dotenv 문법만 지원하고 shell 명령을 실행하지 않는다.

`serve`는 검사 후 현재 Python으로 **고정된 Uvicorn 명령만** 실행한다. controller `192.168.56.10:8000` (workers=1), worker `10.77.0.20:9000`, target `10.78.0.30:8080`이다. 임의 모듈·shell·script 인자를 받지 않는다. child의 working directory는 저장소 루트다. OS/runtime 환경은 유지하되 알려진 모든 서비스 설정과 OpenAI/Azure OpenAI 환경값을 제거한 뒤 선택 파일의 값만 전달한다. 따라서 부모 셸에 남은 시험용 `TARGET_REGISTRY_PATH`나 다른 서비스의 토큰이 조용히 섞이지 않는다. 선택 파일의 누락값을 부모 환경에서 보충하지 않는다.

이 필터는 알려진 애플리케이션 설정의 분리이며 OS 격리나 임의 이름의 모든 비밀 환경 변수 제거를 보장하지 않는다. 서비스마다 별도 VM/계정을 쓰는 기존 경계는 유지한다. Ctrl+C로 자신이 실행한 서비스를 정상 종료한다.

## API 주소·정책·인증 경계

controller의 `WORKER_URL`은 canonical HTTP IP origin, `MCP_WORKER_URL`은 같은 origin의 `/mcp`이어야 한다. URL 자격 증명·DNS·query·fragment와 서로 다른 worker origin을 거절한다. 주소는 운영자 파일의 설정이며 모델/채팅의 동적 URL 입력이 아니다. 실제 worker 접근 제어와 등록 실습 네트워크는 기존 설정을 따른다. 검사 성공을 임의 외부 주소의 실행 승인으로 해석하지 않는다.

worker의 `TARGET_BASE_URL`은 계속 등록 origin과의 **동등성 검사**다. scope 권한은 `config/targets.json` 또는 운영자가 명시한 로컬 registry에서만 온다. 새 검사기는 `worker.registry`와 `worker.limits`를 재사용한다. controller와 target에 정책 사본을 만들지 않았다. HTTP 9회/도구 10회 상한, 전역·프로필·시나리오 최솟값, 전역 rate 0에도 양수 프로필 적용, run snapshot과 재시작 규칙이 유지된다.

`MODEL_PROVIDER=openai` 검사에는 키와 명시적 모델이 필요하지만 검사는 실제 호출을 하지 않는다. UI와 기존 run CLI는 각각의 명시적인 provider 선택을 계속 사용하며 환경 설정만으로 실행을 시작하지 않는다. 기본 provider는 mock이다. 기존 GPT-5.4-mini 결과는 새 설정 경로의 OpenAI 검증 증거가 아니다.

## 기존 배포에서 이전

1. 같은 브랜치 커밋을 기존 git bundle 절차로 전달한다. 인터넷 격리 해제·DNS/방화벽 변경은 필요 없다. 새 Python/venv를 만들지 않는다. `python-dotenv==1.2.4`는 기존 `requirements-full.lock`에도 있던 버전이며 직접 의존성으로 명시했다.
2. 각 서비스의 실제 파일을 자신의 예제와 비교한다. 다른 역할의 키를 해당 VM에서 제거하고 비밀값은 로컬에서 관리한다. controller에는 target DB나 LAB 비밀번호를 복사하지 않는다. 기존 target DB의 비밀번호는 파일 수정만으로 바뀌지 않으므로 일치 여부를 운영자가 확인하고 DB를 삭제하지 않는다.
3. worker의 시험용 registry를 원본으로 복원하려면 `.env.worker`에 `TARGET_REGISTRY_PATH=config/targets.json`을 명시한다. `check worker`로 확인한 뒤 운영자가 기존 worker를 종료하고 새 launcher로 재시작한다. 검사만으로 실행 중 worker가 변경되지는 않는다.
4. controller/target도 각자 `check` 후 정상 재시작한다. 이번 변경은 UI 소스를 수정하지 않았으나 기존 frontend 빌드 산출물을 유지해야 한다. 이미 실행 중인 서비스는 자동 중단하지 않는다.
5. 새 경로에서 mock 허용·계정 거절·한도 차단을 별도로 확인한다. 2026-10-27 fixed UI 두 건은 이전 scope 버전의 사용자 제공 결과이며 이 새 설정 경로를 검증한 것은 아니다.

기존 `uvicorn --env-file ...` 및 `dotenv ... controller.cli` 명령은 호환성을 위해 유지된다. **직접 실행 경로에는 이번 launcher의 엄격한 파일 검사와 부모 환경 필터가 적용되지 않는다.** 기존 명령을 유지할 때는 서비스 전용의 깨끗한 프로세스 환경을 운영자가 보장해야 한다. 설정 변경은 재시작 후 적용된다. 신규 배포에는 위 `check`/`serve` 경로를 권장한다.
