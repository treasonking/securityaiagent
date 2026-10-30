# 로컬 OpenAPI 후보 추출

운영자가 제공한 OpenAPI 3.0.x/3.1.x JSON을 등록 target과 대조한다. 후보는 취약점이나 실행 승인이 아니다. CLI는 로그인·네트워크·모델·서버·DB를 사용하지 않으며 후보 파일을 실행기로 전달하지 않는다. 기존 실행은 UI/CLI에서 별도로 명시해야 한다.

저장소 루트에서 비밀번호·OpenAI 키 없이 실행한다. 출력 부모 폴더는 미리 만들고, 존재하지 않는 JSON 경로를 지정한다. 같은 이름의 Markdown도 생성하며 두 파일 중 하나라도 존재하면 거절한다.

```powershell
.\.venv\Scripts\python.exe -m controller.candidates import-openapi --input examples/openapi/documents.json --registry config/targets.json --target lab-web --output verification_tmp/candidates-documents.json
.\.venv\Scripts\python.exe -m controller.candidates import-openapi --input examples/openapi/records.json --registry config/targets.records.json --target lab-web --output verification_tmp/candidates-records.json
```

Linux는 Python 경로만 `.venv/bin/python`으로 바꾼다. 성공 시 stdout JSON 및 명시한 JSON/Markdown 파일을 출력한다. 오류는 정제된 reason code와 exit 2다. 입력 파일은 복사하지 않는다. 기존 출력은 덮어쓰지 않으며 파일 두 개 생성 중 OS 쓰기 오류가 발생하면 먼저 생성된 파일이 남을 수 있다.

## 해석 범위

- GET, 마지막 단일 path parameter만 후보로 만든다. 다른 메서드와 비후보 GET은 제외 개수로 기록한다. operationId/tags/설명은 후보 준비 상태의 근거가 아니다.
- 이름이 id/recordId/document_id인 차이는 `{document_id}`로 정규화한다. 실제 승인 경로나 wildcard를 수정하지 않는다. path parameter는 required=true, schema는 정확히 string 및 `^doc-[a-z]+-[0-9]{3}$`여야 호환으로 본다. 추가 제약·UUID·숫자 ID는 설정 필요다.
- operation > path > root의 server 우선순위를 적용한다. 생략 시 operator_registry에 바인딩한다. 단일 canonical 등록 origin과 정확히 일치해야 하며 다중/빈 server 배열·변수는 비지원, 외부 origin·다른 port·URL 자격증명·query·fragment는 범위 밖이다.
- 기존 `worker.registry`와 `ApiAdapter` 파서를 재사용한다. Scope 허용 작업·두 계정, 상세 경로, 인증 선언, 로그인 요청 필드, 목록과 상세 응답 매핑을 대조한다. 필수 query/header 또는 상세 requestBody는 공급할 수 없으므로 준비 완료가 아니다.
- documents는 apiKey/cookie `lab_session`, 로그인 Set-Cookie 선언과 기존 평면 목록/상세 매핑에 대응한다. records는 HTTP Bearer, 로그인 `session.access_token`, `data.items` 및 `record.*` 중첩 매핑에 대응한다. 이는 선언과 설정의 대응이며 실제 인증·소유권·비공개 여부 검증이 아니다.
- 객체 JSON Pointer `#/...`만 해석한다. ~0/~1 escape를 지원한다. 원격/file/data ref, 누락, cycle, ref sibling, schema composition(allOf/anyOf/oneOf/not/dynamicRef)은 명시적으로 실패한다. 배열 인덱스 pointer는 지원하지 않는다. 사용하지 않는 구조에서도 지원하지 않는 ref가 발견되면 보수적으로 실패할 수 있다.

| 상태 | 의미 |
|---|---|
| READY_FOR_REVIEW | 등록 읽기 흐름과 선언이 대응하며 운영자 검토 가능; 실행 승인은 아님 |
| NEEDS_CONFIGURATION | 경로·ID·인증·대조군·응답 매핑 등의 대응 미입증 |
| OUT_OF_SCOPE | origin 또는 허용 읽기 작업 불일치 |
| UNSUPPORTED | 후보의 server 구조 등 지원 밖 |

문서 전체를 안전하게 해석할 수 없는 오류는 catalogue 생성 실패로 처리한다. 후보 상태에 Verifier verdict를 쓰지 않으며 항상 `verification_status=NOT_EXECUTED`다.

## 상한과 데이터 경계

### 로그인 인증과 대조군 타입 확인 (검토 보완)

로그인은 operation의 `security`가 있으면 그것을 사용하고, 없으면 root `security`를 상속한다. 양쪽 모두 생략하거나 유효한 `security: []`이면 익명 로그인으로 해석한다. 요구사항 배열은 OR, 각 객체 안의 scheme은 AND다. 현재 로그인은 사전 토큰/API 키를 공급하지 않으므로 유효한 빈 객체 `{}` 대안이 있어야 OR 요구사항을 충족할 수 있다. 인증만 있는 OR나 비어 있지 않은 AND는 `NEEDS_CONFIGURATION / LOGIN_AUTH_UNPROVEN`이다.

지원하는 로그인 보안 선언 부분집합은 등록된 apiKey(header/cookie/query, 비어 있지 않은 name), HTTP basic/bearer 및 빈 scopes 배열이다. 익명 대안이 있더라도 **모든 선언 분기**의 구조·scheme 등록·scopes를 검사한다. 미등록 scheme, null/잘못된 security 구조, 잘못된 scopes, 비지원 OAuth/OpenID 등의 분기가 있으면 준비 완료로 처리하지 않는다. GET/목록 인증의 기존 단일 어댑터 대응 규칙은 그대로다. 새 인증값 입력이나 로그인 실행 기능은 없다.

Bearer 토큰, 목록 계정·리소스·소유자 ID는 명확한 비-null string이어야 한다. 목록은 array, 각 item과 selector가 통과하는 부모는 명시적 object여야 한다. Set-Cookie 응답 선언도 string이어야 한다. 타입 누락·union·nullable·모순된 properties/items를 허용하지 않으며 `CONTROLS_UNPROVEN`으로 남긴다. 이 엄격한 부분집합 밖의 유효 OpenAPI도 설정 검토가 필요할 수 있다. 선언 대응은 실제 토큰 발급·소유권·비공개 여부의 검증이 아니다.

입력 2 MiB, 깊이 64, operations 1,000, ref chain 16, ref 방문 10,000, 확장 노드 100,000, 후보 100이다. 하나라도 초과하면 실패하며 조용히 잘라내지 않는다. 성공 결과의 partial은 false다. JSON 중복 키, NaN/Infinity/숫자 overflow, 버전·구조 오류도 거절한다. 입력과 registry는 일반 로컬 파일이어야 하며 명시적 URI·UNC·직접 symlink를 거절한다. 운영자는 입력 부모 디렉터리도 로컬 저장소로 관리해야 한다. OS 파일시스템 격리 기능은 아니다.

description/summary/example/default/확장 필드는 실행하거나 출력하지 않는다. 임의 명세 경로에서 비밀을 완벽하게 탐지한다고 주장하지 않는다. 더 보수적으로 **등록 상세 경로와 일치하는 경로만 출력**하고 다른 후보는 path_template=null 및 구조 digest로 식별한다. 원문 서버 URL·parameter 이름·입력 오류 내용도 출력하지 않는다.

source_sha256은 원본 bytes, candidate_id는 정규화한 method/path/target 구조의 digest다. 공백·키 순서 변경은 source digest를 바꾸지만 candidate ID를 바꾸지 않는다. registry_sha256은 선택한 target의 origin/profile/adapter 정규화 digest이며 worker run snapshot이나 실효 한도 계산값이 아니다. 기존 결과는 별도 값으로 반환돼 파일 변경으로 사후 수정되지 않는다.

명세·편집한 catalogue는 권한이 아니다. Scope/어댑터 자동 수정, 후보 실행, HAR/YAML/원격 다운로드/브라우저 탐색/외부 API 지원은 추가하지 않았다. [실제 검증 결과](../reports/openapi_candidate_verification.md)를 참고한다.
