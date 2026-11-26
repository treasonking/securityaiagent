# 저장된 합성 사례 판정 감사

감사 결과 **통과**. 저장 run 평가 14/14건. 실행 전 거절 2건은 판정·미리보기 분모에서 제외했다.

| 사례 | 기대 판정 | 현재 결론 | 일치 | 초안 미리보기 | 사유 |
|---|---|---|---|---|---|
| cookie-vulnerable-function-normal | VULNERABLE | VULNERABLE | 예 | 허용 | CROSS_ACCOUNT_PRIVATE_PROOF |
| cookie-vulnerable-mcp-normal | VULNERABLE | VULNERABLE | 예 | 허용 | CROSS_ACCOUNT_PRIVATE_PROOF |
| cookie-fixed-function-normal | BLOCKED_BY_ACCESS_CONTROL | BLOCKED_BY_ACCESS_CONTROL | 예 | 거절 | DRAFT_BLOCKED |
| cookie-fixed-mcp-normal | BLOCKED_BY_ACCESS_CONTROL | BLOCKED_BY_ACCESS_CONTROL | 예 | 거절 | DRAFT_BLOCKED |
| bearer-vulnerable-function-normal | VULNERABLE | VULNERABLE | 예 | 허용 | CROSS_ACCOUNT_PRIVATE_PROOF |
| bearer-vulnerable-mcp-normal | VULNERABLE | VULNERABLE | 예 | 허용 | CROSS_ACCOUNT_PRIVATE_PROOF |
| bearer-fixed-function-normal | BLOCKED_BY_ACCESS_CONTROL | BLOCKED_BY_ACCESS_CONTROL | 예 | 거절 | DRAFT_BLOCKED |
| bearer-fixed-mcp-normal | BLOCKED_BY_ACCESS_CONTROL | BLOCKED_BY_ACCESS_CONTROL | 예 | 거절 | DRAFT_BLOCKED |
| cookie-vulnerable-function-budget2 | INCONCLUSIVE | INCONCLUSIVE | 예 | 거절 | DRAFT_NOT_COMPLETED |
| cookie-vulnerable-mcp-budget2 | INCONCLUSIVE | INCONCLUSIVE | 예 | 거절 | DRAFT_NOT_COMPLETED |
| cookie-vulnerable-function-owner_mismatch | INCONCLUSIVE | INCONCLUSIVE | 예 | 거절 | DRAFT_UNCONFIRMED |
| cookie-vulnerable-mcp-owner_mismatch | INCONCLUSIVE | INCONCLUSIVE | 예 | 거절 | DRAFT_UNCONFIRMED |
| cookie-vulnerable-function-proof_rotation | INCONCLUSIVE | INCONCLUSIVE | 예 | 거절 | DRAFT_UNCONFIRMED |
| cookie-vulnerable-mcp-proof_rotation | INCONCLUSIVE | INCONCLUSIVE | 예 | 거절 | DRAFT_UNCONFIRMED |

## 기대 판정 × 현재 결론

| 기대 ＼ 현재 | VULNERABLE | BLOCKED_BY_ACCESS_CONTROL | INCONCLUSIVE |
|---|---:|---:|---:|
| VULNERABLE | 4 | 0 | 0 |
| BLOCKED_BY_ACCESS_CONTROL | 0 | 4 | 0 |
| INCONCLUSIVE | 0 | 0 | 6 |

평가 가능한 14건 중 잘못 허용한 초안 0건, 잘못 거절한 초안 0건. 전체 사례 중 평가 불가 0건.

## 실행 전 정책 거절 확인

- cookie-vulnerable-function-policy_change · WORKER_POLICY_CHANGED
- cookie-vulnerable-mcp-policy_change · WORKER_POLICY_CHANGED

## 임시 사본에서 증거 한 건 누락

cookie-vulnerable-function-normal · 통과
- 증거 11 → 10개. 현재 결론 INCONCLUSIVE (REPORT_CONTRACT_MISMATCH). 초안 미리보기 거절 (DRAFT_UNCONFIRMED).

이 수치는 2026-11-13에 저장한 합성 사례의 오프라인 회귀 결과다. 모델 탐지율, 외부 서비스 성능, 실제 초안 다운로드는 평가 범위 밖이다.
