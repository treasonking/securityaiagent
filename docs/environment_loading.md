# VM별 환경변수 로딩과 실행

SecurityLab은 `.env`를 애플리케이션 코드에서 자동 로드하지 않는다. 비밀을 한 파일에 모아 모든 VM에 복사하지 말고 `.env.target`, `.env.worker`, `.env.controller`를 각 VM에만 만든다. 세 파일은 Git에 커밋하지 않는다.

## target VM

```dotenv
TARGET_MODE=vulnerable
TARGET_DATABASE_PATH=data/target.sqlite3
LAB_USER_A_PASSWORD=...
LAB_USER_B_PASSWORD=...
LAB_ADMIN_PASSWORD=...
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn target.app:app --env-file .env.target --host 10.78.0.30 --port 8080
```

```bash
.venv/bin/python -m uvicorn target.app:app --env-file .env.target --host 10.78.0.30 --port 8080
```

## worker VM

```dotenv
WORKER_TOKEN=충분히-긴-controller와-공유한-토큰
TARGET_BASE_URL=http://10.78.0.30:8080
LAB_USER_A_PASSWORD=...
LAB_USER_B_PASSWORD=...
LAB_ADMIN_PASSWORD=...
WORKER_ALLOWED_CLIENTS=10.77.0.10,127.0.0.1,::1
MCP_ALLOWED_HOSTS=10.77.0.20:9000,127.0.0.1:*,localhost:*,[::1]:*
MCP_ALLOWED_ORIGINS=http://10.77.0.10:8000
HTTP_MAX_REQUESTS=30
AGENT_MAX_STEPS=12
HTTP_TIMEOUT_SECONDS=5
RUN_TIMEOUT_SECONDS=180
HTTP_MAX_RESPONSE_BYTES=65536
HTTP_MAX_CONCURRENCY=1
HTTP_REQUESTS_PER_SECOND=2
WORKER_MAX_RUNS=100
WORKER_STATE_TTL_SECONDS=600
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn --factory worker.app:create_app_from_env --env-file .env.worker --host 10.77.0.20 --port 9000
```

`MCP_ALLOWED_HOSTS`에는 실제 worker의 Host 헤더만 정확히 등록한다. `*` 전체 Host나 DNS rebinding 보호 비활성화는 사용하지 않는다. `127.0.0.1:*`와 `localhost:*`는 로컬 회귀 시험 전용이다.

## controller VM

```dotenv
WORKER_TOKEN=worker와-동일한-토큰
WORKER_URL=http://10.77.0.20:9000
MCP_WORKER_URL=http://10.77.0.20:9000/mcp
APP_SESSION_SECRET=24자-이상의-무작위-서명키
APP_ACCESS_TOKEN=16자-이상의-초기-접근-토큰
APP_SESSION_TTL_SECONDS=3600
APP_SECURE_COOKIE=false
OFFLINE_VERIFICATION_TOKEN=evaluator와-공유한-별도-토큰
UI_ALLOWED_ORIGINS=http://192.168.56.10:8000
UI_ALLOWED_HOSTS=192.168.56.10
CONTROLLER_ALLOWED_CLIENTS=192.168.56.1
DATABASE_PATH=data/securitylab.sqlite3
RUN_MAX_CONCURRENCY=1
CONTROLLER_RUN_TIMEOUT_SECONDS=180
MODEL_PROVIDER=mock
OPENAI_MODEL=
OPENAI_API_KEY=
MODEL_MAX_CALLS=8
```

```powershell
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn --factory controller.api:create_app_from_env --env-file .env.controller --host 192.168.56.10 --port 8000 --workers 1
```

HTTP Host-only 데모에서는 `APP_SECURE_COOKIE=false`를 사용한다. TLS reverse proxy를 정확히 구성한 배포에서만 `true`로 바꾼다. 여러 Uvicorn worker를 사용하면 프로세스 내부 run queue와 세션 폐기 상태가 공유되지 않으므로 v1은 반드시 `--workers 1`로 실행한다.

## CLI에서 환경 파일 로드

Uvicorn의 `--env-file`은 Uvicorn으로 시작할 때만 적용된다. CLI는 실행 전에 현재 프로세스 환경으로 명시적으로 로드한다.

PowerShell:

```powershell
Get-Content .env.controller | Where-Object { $_ -and -not $_.StartsWith('#') } | ForEach-Object {
  $name, $value = $_.Split('=', 2)
  [Environment]::SetEnvironmentVariable($name, $value, 'Process')
}
.\.venv\Scripts\python.exe -m controller.cli doctor
```

Linux shell:

```bash
set -a
. ./.env.controller
set +a
.venv/bin/python -m controller.cli doctor
```

`doctor`는 worker health가 실패하거나 `WORKER_TOKEN`이 없으면 이제 0이 아닌 종료 코드를 반환한다.
