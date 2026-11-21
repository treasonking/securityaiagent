# 저장된 합성 검사 초안 검증 · 2026-11-20

PR #8의 `70b2da4967f55a684b49e3ddb2afc88b5d7cee37`에서 시작했다. 기존 독립 API 검증 기록의 임시 사본을 사용했다. 이번 검증은 저장 자료의 조회와 초안 발급에 한정했다.

## 브라우저에서 확인한 파일

Windows의 headless Chrome 157.0.8103.79에서 임시 loopback Controller와 빌드된 UI를 사용했다. 임시 로그인 세션으로 저장 검사 `run_e573a6e9ec6d4823a48fe554e6b0790f`를 열었다. UI 확인란 선택 전에는 다운로드 버튼이 비활성화됐다. 선택 후 받은 파일의 UTF-8 바이트가 미리보기 전문과 일치했고, 본문의 run ID와 교차 조회 근거를 확인했다. 파일명은 `run_e573a6e9ec6d4823a48fe554e6b0790f-internal-draft.md`였다. 아래 예시는 그 파일의 사본이다.

- 크기 2,219바이트
- SHA-256 `ed2bf1e5521a6544c7be3e60c58c35544cf6b3daf500398a2c7a6c155d6c9c56`
- 검사 원본 [cookie-vulnerable-function-normal](../independent_api_validation_20261113/cookie-vulnerable-function-normal/runs/run_e573a6e9ec6d4823a48fe554e6b0790f)
- [다운로드한 Markdown](example.md)

## API 회귀와 빌드

| 조건 | 관측 결과 |
|---|---|
| 완료 · 최초/재판정 모두 취약 | 미리보기와 다운로드 일치. 발급 시 각 JSON 입력을 한 번씩 읽었고 원본 파일 바이트 보존 |
| 차단, 미완료, 보류, 판정 불일치, 필수 자료 읽기 실패 | 미리보기와 발급 모두 HTTP 409. 사유 코드 반환 |
| 검토 후 교차 요청의 request ID만 변경 | 재판정은 취약으로 유지. 이전 확인값은 409, 새 확인값은 발급 성공 |
| 검토 후 증거 한 건 누락 | 재판정 보류로 발급 거절 |
| 다른 run의 확인값 또는 템플릿 버전 변경 | 409 `DRAFT_REVIEW_CHANGED` |
| 로그인 누락, CSRF 누락, 잘못된 Origin | 각각 401, 403, 403 |
| 확인 누락·거짓, 초안 본문 바꿔치기 인자 | 422 |

관련 백엔드 테스트 22개와 프런트엔드 테스트 22개가 통과했고 프로덕션 빌드가 성공했다. 최종 파일에서 임시 접근 토큰, 저장 증거의 proof digest 및 세션 바인딩이 제외됐음을 대조했다. API 회귀에서도 임의의 비공개 보고서 필드가 미리보기와 발급물에 없는지 확인했다.

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q tests/test_disclosure_draft.py tests/test_workspace_saved_conclusion.py tests/test_controller_api.py::test_csrf_and_session_are_required tests/test_controller_api.py::test_controller_rejects_untrusted_host_and_client
npm --prefix frontend test
npm --prefix frontend run build
```

브라우저 확인은 저장된 취약 사례 한 건에 대해 수행했다. 거절 조건은 오프라인 API 테스트에서 검증했다. 검토 확인값은 내용의 동일성을 비교한다. 증거의 출처나 검토자의 신원을 증명하는 서명, 실제 고객에 대한 영향 평가는 범위 밖이다.
