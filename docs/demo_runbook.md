# Demo runbook

1. 세 VM의 snapshot과 network/firewall 상태를 콘솔에서 확인한다.
2. target에서 `python -m target.cli reset`을 실행한다.
3. target을 `TARGET_MODE=vulnerable`로 시작한다.
4. worker와 controller를 시작하고 `python -m controller.cli doctor` 결과를 저장한다.
5. UI에서 `lab-web`, `access-control`, mock, function을 실행한다.
6. 후보와 verifier 확정 판정, safe controls, cross-account evidence를 펼쳐 보인다.
7. target 콘솔에서 종료하고 `TARGET_MODE=fixed`로 재시작한 뒤 reset한다.
8. 동일 입력·scenario·limits로 다시 실행해 `BLOCKED_BY_ACCESS_CONTROL`을 확인한다.
9. mock+MCP 경로를 별도로 실행해 transport 동등성을 확인한다.
10. target-local DB로 offline verifier를 실행하고 online 결과와 상관 상태를 비교한다.

발표 시 다음을 명시한다.

- HTTP 요청은 실제 synthetic target에 전송된다. 모델은 mock일 수 있다.
- mock은 로컬 LLM이 아니며 AI 성능 평가 대상이 아니다.
- MCP는 도구 규약이고 권한 제어를 대체하지 않는다.
- Nmap/Playwright, VM 격리, live OpenAI 결과는 증거가 없으면 완료로 말하지 않는다.
