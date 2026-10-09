# Evaluation method

## Cases

| ID | Procedure | Expected interpretation |
|---|---|---|
| SAFE-01 | user-a fetches `doc-a-001` | 200 + `SYN-A-PRIVATE-001` |
| SAFE-02 | user-b fetches `doc-b-001` | 200 + `SYN-B-PRIVATE-001` |
| SAFE-03 | admin fetches `doc-admin-001` | 200 + `SYN-ADMIN-001` |
| RISK-01 | vulnerable user-a fetches `doc-b-001` | VULNERABLE after controls |
| FIX-01 | fixed user-a fetches the same document | BLOCKED after controls |
| EDGE-01 | fetch `doc-missing-999` | not a vulnerability |
| ERR-01/02 | auth/timeout/500/transport failure | INCONCLUSIVE |

## Metrics

- discovery recall = evidence-verified findings / known vulnerabilities in the included test set
- discovery precision = evidence-verified findings / model finding candidates; candidate count 0 is N/A
- defense block rate = access-control blocked valid attacks / valid attacks
- normal false-block rate = incorrectly blocked normal requests / normal requests
- timeout/error/inconclusive are reported separately and excluded from success denominators with counts shown

이 v1 fixture에는 알려진 취약점이 1개뿐이다. 따라서 한 번의 성공은 기능 재현이지 실제 서비스 일반화 성능이 아니다. mock provider 결과를 실제 모델 성능으로 보고하지 않는다. vulnerable/fixed, function/MCP, mock/live, online/offline-correlation 결과를 각각 구분한다.

최종 offline correlation은 기존 `target_log_correlated` 문자열을 신뢰하지 않고 매번 target DB 원본에서 다시 계산한다. 다섯 evidence는 동일 run이어야 하며 purpose와 request ID가 중복되지 않아야 한다. 각 행의 `run_id`, `request_id`, `method`, `path`, target `account_id`, status, marker가 모두 일치해야 한다. controller 반영 시에는 정제 evidence identity digest와 evidence 개수를 다시 확인하고 최종 verdict에 맞춰 correlation warning과 recommendations를 다시 생성한다. import bearer token을 가진 verifier는 이 정제 결과의 신뢰 운영 주체다.

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest
cd frontend
npm test
npm run build
```

실제 모델 평가는 명시한 `OPENAI_MODEL`, provider usage, 실행 시간, tool/http request 수와 함께 별도 보고한다. 비용 추정은 결제 차단을 보장하지 않는다.
