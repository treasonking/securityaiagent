# OpenAPI 후보 importer 검증 — 2026-10-31

## 검토 보완 — 로그인 요구사항 및 대조군 타입

검토 기준 `fd86c33`에서 로그인 자체의 security를 검사하지 않아 추가 API 키·root 인증 상속을 준비 완료로 분류했고, 일부 토큰·목록 필드는 존재 여부만 검사했다. 로그인 operation/root 우선순위 및 익명 OR 대안 해석, 모든 보안 분기 구조 검사와 고정 reason code를 추가했다. 토큰·목록 ID/소유자/계정의 string 및 부모 object/목록 array 구조를 강제했다. 후보 schema·구조 ID·Scope 권한·실행 엔진은 변경하지 않았다.

최종 집중 검사: `.\.venv\Scripts\python.exe -m pytest tests/test_candidates.py --tb=short` → **164 passed, 3.86초**. 두 API의 추가 API 키·root Bearer 상속·익명/OR/AND·잘못된 security/scopes, records 토큰 및 양 API의 목록 타입·중첩 구조, cookie 응답 타입을 검사했다. 기존 socket/HTTP/OpenAI/subprocess/Uvicorn/SQLite 부작용 감시를 유지했다. 수정 전 새 시험에서 잘못된 READY 분류를 재현한 뒤 수정했으며, 정상 array를 음성 입력으로 취급했던 테스트 조합도 모순된 객체 구조를 명시하도록 바로잡았다.

기본 CLI를 기존 결과를 덮어쓰지 않는 새 임시 경로로 재실행했다:

```powershell
.\.venv\Scripts\python.exe -m controller.candidates import-openapi --input examples/openapi/documents.json --registry config/targets.json --target lab-web --output verification_tmp/review-fixes-documents.json
.\.venv\Scripts\python.exe -m controller.candidates import-openapi --input examples/openapi/records.json --registry config/targets.records.json --target lab-web --output verification_tmp/review-fixes-records.json
```

각각 후보 1건, READY_FOR_REVIEW / NOT_EXECUTED를 유지했다. candidate ID도 기존 documents `6b1a0af20067f1610b3cba91f505f21b246128a85fc3099ef6315fafe72b6928`, records `38eae30a50bfb3b8b5cebc483cd96e63b9cd712af75c798eecf59f0413273b89`와 같다. source_sha256은 원본 bytes digest이며 OS 개행 변화에도 달라질 수 있어 구조 ID 안정성과 별개다. 임시 출력은 Git에 포함하지 않으며 기존 저장된 후보 예제는 유지했다.

최종 전체 회귀 `.\.venv\Scripts\python.exe -m pytest --tb=short`: **496 passed, 7 warnings, 178.86초**. 기존 MCP/Pydantic 의존성 경고이며 실패는 없었다. 위 집중 검사와 동일한 최종 코드로 실행했다. 프런트엔드 `npm run build`도 성공했다. 전체 회귀의 기존 로컬 TCP·임시 DB 테스트 외에 VM·기존 환경파일·DB 변경·유료 모델·외부 서비스 테스트는 수행하지 않았다. 이전 TCP·VM 증거를 이 검사의 증거로 재사용하지 않는다. 아래 최초 구현의 검사 수는 당시 이력이며 이번 수치와 합산하지 않는다.

## 최초 구현 이력

기준 `codex/target-api-adapters`의 최신 원격 `bb39b1d`를 fetch·대조한 뒤 `codex/openapi-candidate-import`에서 작업했다. 로컬 Windows, Python 3.12.14, Node v22.18.0 및 기존 잠금 의존성을 사용했으며 새 의존성은 없다. VM 설정·실제 환경파일·기존 DB는 수정하지 않았다.

## 직접 실행한 오프라인 CLI

저장소 루트에서 다음 명령을 실행했다. 새 출력 디렉터리 `reports/openapi_candidates`를 먼저 생성했다.

```powershell
.\.venv\Scripts\python.exe -m controller.candidates import-openapi --input examples/openapi/documents.json --registry config/targets.json --target lab-web --output reports/openapi_candidates/documents.json
.\.venv\Scripts\python.exe -m controller.candidates import-openapi --input examples/openapi/records.json --registry config/targets.records.json --target lab-web --output reports/openapi_candidates/records.json
```

| 합성 fixture | 예상 및 실제 후보 | 상태 | 제외 |
|---|---|---|---|
| documents | `/documents/{document_id}` 1건 | READY_FOR_REVIEW / NOT_EXECUTED | 로그인 POST 1건, 목록 GET 1건 |
| records | `/api/records/{document_id}` 1건 | READY_FOR_REVIEW / NOT_EXECUTED | 로그인 POST 1건, 목록 GET 1건 |

증거: [documents JSON](openapi_candidates/documents.json), [Markdown](openapi_candidates/documents.md), [records JSON](openapi_candidates/records.json), [Markdown](openapi_candidates/records.md). 모두 서버 생략을 operator_registry로 기록했고 network_requests=0, model_calls=0이다. mode는 importer 입력이 아니므로 vulnerable/fixed를 구분하거나 판정하지 않는다. fixture 두 개의 대응을 외부 API 일반화 성능으로 표현하지 않는다.

## 회귀와 부작용 감시

`tests/test_candidates.py`는 socket, HTTP client send, OpenAI client 생성, subprocess 생성, Uvicorn 시작, SQLite 연결을 실패하도록 감시한다. 기본/실패 경로가 모두 이 감시 아래 수행되며 importer의 해당 부작용은 0회다. 기존 전체 회귀의 TCP 네트워크 테스트는 별개다.

시험 범위: 두 API 정확한 후보·제외 집합, 공백/순서 변경의 candidate ID 안정성과 source digest 변화, origin/port/자격증명/query/fragment, server 상속과 우선순위, UUID/필수 입력/인증 모호성/매핑 누락, 미등록 경로 정제, 상태 변경 메서드 제외, remote/file/data/missing/cycle ref, 모든 상한, 중복 JSON/NaN/overflow/버전 오류, 비신뢰 설명 유출 방지, registry mismatch 및 변경 없음, CLI 출력 덮어쓰기 거절.

전체 `.\.venv\Scripts\python.exe -m pytest --tb=short`: **370 passed, 7 warnings, 182.79초**. 기존 MCP/Pydantic 의존성 경고이며 실패는 없었다. 이후 명시적 UNC·URI 및 비정규 파일 입력 거절을 보강하고 importer 전체를 재검사한 결과: **43 passed, 2.48초** (`tests/test_candidates.py`). 전체 회귀 수와 마지막 보강 후 집중 검사 수를 구분한다. `frontend`의 `npm run build`도 성공했다. UI 소스 변경·새 UI 테스트·브라우저 설치는 없었다.

pytest는 기존 Windows 임시 디렉터리 권한 문제를 피하도록 `PYTEST_DEBUG_TEMPROOT=verification_tmp`의 절대 경로와 `-o cache_dir=verification_tmp/pytest-cache`를 사용했다. 기존 회귀에 포함된 TCP 검사는 수행했지만 별도 TCP 행렬 스크립트를 추가 재실행하지 않았다.

## 미검증 범위 및 다음 단계

실제 서비스 명세, VM importer 실행, 외부 서비스·OpenAI·브라우저 탐색과 후보 선택→자동 실행 연결은 미검증/미구현이다. 기존 VM 정상 8건은 사용자 제공 UI·Controller 재판정 출력이며 importer의 증거가 아니다. 기존 로컬 TCP 16건, OpenAI 결과와 실패 이력은 수정하지 않았다. 새 어댑터의 VM 계정 거절·한도 차단도 미검증으로 유지한다.

다음 단계는 운영자가 정제된 후보와 NEEDS_CONFIGURATION 사유를 검토하는 것이다. 실행 연결은 별도 설계·승인 작업으로 남긴다. 지원 부분집합과 오류 계약은 [운영 문서](../docs/openapi_candidate_import.md)에 있다.
