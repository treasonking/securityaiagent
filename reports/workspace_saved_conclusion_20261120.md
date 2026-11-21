# 저장 증거와 공유 보고서의 판정 · 2026-11-20

기준 커밋 `09a94fead6f5a1d2bfcddb720df3ed022de66d28`에서 보관된 합성 cookie/function run 두 개를 임시 디렉터리에 복사했다. 수정 전에 마지막 HTTP 증거 한 건을 제거하자 두 사본 모두 replay가 `INCONCLUSIVE / REPORT_CONTRACT_MISMATCH`였으나, JSON 영향 문구는 각각 비공개 proof 일치 또는 명시적 거절을 단정했다. 재현 테스트는 두 경우 모두 실패했다.

| 임시 사본 조건 | 수정 후 상세·목록과 다운로드 |
|---|---|
| 원본 취약 / 차단, 증거 온전 | 각각 VULNERABLE / BLOCKED_BY_ACCESS_CONTROL 일치. 구형 보고서의 버전 표시는 not-recorded 유지 |
| 원판정만 반대로 변경, 양방향 | 판정 보류 / 증거 불일치, VERDICT_MISMATCH. replay가 확정형이어도 현재 결론은 INCONCLUSIVE |
| 마지막 증거 누락, 두 원판정 | 판정 보류 / 증거 불일치, REPORT_CONTRACT_MISMATCH. 영향·권고에도 보류 사유 표시 |
| 증거 파일 없음, 읽기 거부, 계약 JSON 파싱 실패 | 식별된 목록 항목은 검증 불가. 상세 및 두 다운로드는 HTTP 409 SAVED_INPUT_UNREADABLE |
| report.json 없음 | operator 목록에서 제외. 해당 디렉터리의 상세·다운로드는 동일한 정제 오류 |

FastAPI 인프로세스 요청으로 목록·상세와 Markdown/JSON 두 형식을 확인했다. 반복 다운로드 결과는 바이트 단위로 같았고 사본의 파일 목록과 내용도 조회 전후 동일했다. CLI replay와 상세 replay도 대조했다. 프런트엔드는 목록 버튼과 상세 제목의 실제 React 컴포넌트를 정적 렌더링했다.

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -o addopts= -q tests/test_workspace_saved_conclusion.py tests/test_operator_workspace.py::test_server_only_profile_config_and_symlink_containment
cd frontend
npm test
npm run build
```

관련 백엔드 11개와 프런트엔드 22개가 통과했고 TypeScript 및 Vite 빌드가 성공했다. 실제 브라우저 E2E는 수행하지 않았다. 이번 검증은 저장된 증거 조회만 다뤘으며 검사 엔진 실행, 모델 호출, VM 배포와 네트워크 대상 접속은 없었다.
