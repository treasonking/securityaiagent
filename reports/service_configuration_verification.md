# 서비스별 API·인증 설정 분리 검증 — 2026-10-27

기준은 원격과 일치한 `codex/scope-policy`의 `f21c8e5`다. HTTP 검증, compact chat UI, scope 구현 및 기존 VM 결과를 모두 포함한 상태에서 새 `codex/service-auth-config` 브랜치를 생성했다. main 병합이나 VM 배포는 수행하지 않았다.

## 변경

- 사용자 제공 fixed VM UI 두 건을 [scope 검증 결과](scope_policy_verification.md)와 [증거 색인](evidence_index.md)에 먼저 추가했다. 두 run은 mock, lab-access-control r1, BLOCKED_BY_ACCESS_CONTROL, 증거 7개, http_observation이다. UI 상한은 사용량이 아니므로 HTTP/도구 실측값이나 정책 hash를 추정하지 않았다.
- 통합 환경 예제를 `.env.controller.example`, `.env.worker.example`, `.env.target.example`로 나눴다. `.env.example`은 이전 안내로 바꿨고 실제 `.env.*`는 수정하지 않았다. 세 예제만 Git 추적 예외이며 실제 비밀 파일은 ignore된다.
- `common/service_config.py`는 서비스별 허용 키·필수 비밀값·controller API 주소/인증 경계를 검사한다. 중복/unknown/다른 역할 키·환경 치환을 거절하며 오류는 값을 출력하지 않는다. controller/worker의 WORKER_TOKEN과 worker/target의 계정 비밀번호 공유 경계는 유지한다.
- `check`는 네트워크와 서비스/DB 초기화 없이 검사한다. `serve`는 선택 파일만 전달해 고정 Uvicorn 명령을 실행한다. 자식 프로세스에서 알려진 다른 앱 환경과 OpenAI 환경값을 제거한다. 전역 부모 환경은 바꾸지 않는다. 임의 shell/모듈/script 실행 옵션은 없다.
- worker는 기존 scope registry와 동일한 전역 한도 파서를 재사용한다. `limits_from_env`에 명시적 mapping 인자만 추가했으며 기존 무인자 환경 로딩 경로를 유지했다. 프로필 권한을 다른 파일에 복제하지 않았다.
- `python-dotenv==1.2.4`는 기존 full lock의 버전을 직접 의존성으로 명시했다. 설치나 업그레이드를 실행하지 않았다. [운영 가이드](../docs/service_configuration.md)에 Windows/Ubuntu 검사·기동 및 기존 명령 호환 범위를 기록했다.

## 실제 로컬 검사

| 명령/검사 | 결과 |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests/test_service_config.py --tb=short` | 31 passed, 1.25초 |
| `.\.venv\Scripts\python.exe -m pytest --tb=short` | **284 passed**, 7 warnings, 150.93초 |
| frontend `npm test` | **14 passed** |
| frontend `npm run build` | TypeScript/Vite build 성공 |
| `git diff --check` | 성공 |
| `git check-ignore .env.controller .env.worker .env.target` | 실제 환경 파일 세 경로 ignore 확인 |

Windows에서 `PYTHONUTF8=1`, `PYTEST_DEBUG_TEMPROOT=<workspace>/verification_tmp`, `PYTEST_ADDOPTS=-o cache_dir=verification_tmp/pytest-cache`를 설정했다. 7 경고는 기존 Pydantic lifespan forward-reference 1회 및 deprecated SDK transport helper 6회다. 실패는 없었다. 이전 253개 테스트/VM 기록을 이번 테스트로 덮어쓰지 않았다.

신규 31개는 역할별 키·비밀 노출 방지, 파일 문법/중복/치환 거절, 누락 인증값, 같은 토큰의 다른 인증 경계 재사용, 명시적 OpenAI 키/모델 요구(가짜 값만 사용), worker function/MCP origin 일치, scope 동등성 검사, 낮은 HTTP 한도/전역 rate 0, 부모 환경 필터·고정 프로세스 명령, 잘못된 파일의 실행 차단을 검증한다. target 오프라인 검사는 실제 별도 Python 프로세스로 실행했고 DB가 생성되지 않음을 확인했다. launcher의 `serve` 테스트는 프로세스 호출을 대체해 명령/전달 환경을 검사했으며 실제 VM listener를 시작하지 않았다.

전체 회귀에는 기존 로컬 TCP mock 네 조합·REST/MCP 인증·scope 거절·HTTP 판정·로그 기반 판정·offline import·privacy/UI 계약 검사가 포함된다. 이 회귀를 새 launcher를 통한 실제 VM 기동 증거로 표현하지 않는다.

## 한계와 다음 작업

새 서비스 설정 경로의 실제 VM 기동·인증 연결, 실제 브라우저 E2E, 추가 OpenAI 호출 및 외부 사이트는 미검증이다. 테스트용 비밀값 외에 실제 비밀을 읽거나 공개하지 않았고 VM/네트워크/DB 변경을 수행하지 않았다. known-key 환경 필터는 OS sandbox가 아니며 임의 이름의 모든 비밀 제거를 보장하지 않는다. 기존 직접 Uvicorn/CLI 경로는 호환되지만 새 검사/필터를 우회한다는 점을 운영 가이드에 명시했다.

다음은 운영자가 각 VM의 실제 설정을 역할별 예제와 대조하고, 새 `check` 성공 후 자신의 서비스를 정상 재시작해 mock 허용·거절·한도를 확인하는 작업이다. 기존 DB/환경 파일을 자동 덮어쓰거나 삭제하지 않는다. 사용자 제공 fixed UI 두 건은 이전 scope 실행의 증거로 보존하며 이 새 구현의 VM 검증에 재사용하지 않는다.
