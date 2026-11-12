# Codex 인계: 입력칸이 항상 보이는 채팅 레이아웃

## 문제와 변경

기존 shell은 min-height: 100vh만 지정하고 workspace의 가운데 행을 1fr로 두었다. 결과 카드와 대화가 쌓일 때 문서 전체 높이가 늘어나 입력칸이 화면 아래로 밀렸다.

- shell을 100dvh(100vh fallback) 높이로 제한했다.
- workspace는 auto / minmax(0, 1fr) / auto로 배치한다. 헤더와 입력 영역은 남고 대화·결과만 내부 스크롤된다.
- sidebar의 긴 대화 목록은 별도로 스크롤한다.
- 대화·결과·입력 영역의 과도한 여백을 줄였다.
- 입력칸은 기본 1행·최소 44px로 시작한다. 내용 및 창 너비 변화에 맞춰 커졌다가 줄어든다. 최대 높이는 화면 높이의 24%, 상한 160px이며 초과 내용은 입력칸 안에서 스크롤한다.
- 좁은 화면에서도 실행 버튼을 입력칸 옆에 유지하고, 설정 선택기는 가로 스크롤한다.
- 인증, API, 모델, worker, target, 시나리오와 저장된 증거는 변경하지 않았다.

## 수정 파일

- frontend/src/App.tsx
- frontend/src/styles.css
- 이 인계 문서

## 검증과 한계

기존 React/Node 테스트 12개 및 TypeScript/Vite 빌드를 실행해 통과했다. 마지막 소스 변경 뒤에도 같은 검증을 재실행한다. git diff --check로 공백 오류를 확인한다.

실제 브라우저 화면 검증은 미완료다. 검증 환경에 Chromium이 없었고 다운로드가 정상 ZIP을 반환하지 않아 실행할 수 없었다. Node 소스 계약 테스트를 브라우저 E2E로 주장하지 않는다. 제품의 Playwright 보안 도구를 추가한 변경이 아니다.

## controller VM에 적용

worker/target 갱신이나 VM 네트워크 변경은 필요 없다. controller에서 사용자 변경이 없는지 확인한 뒤 실행한다. 오류나 변경 파일이 있으면 강제 초기화하지 않는다.

```bash
cd ~/securityaiagent
git status --short
git fetch origin
git switch codex/compact-chat-layout
git pull --ff-only origin codex/compact-chat-layout
cd frontend
npm ci
npm run build
```

controller 서버를 기존 터미널에서 Ctrl+C로 종료하고 다시 시작한다.

```bash
cd ~/securityaiagent
.venv/bin/python -m uvicorn --factory controller.api:create_app_from_env \
  --env-file .env.controller --host 192.168.56.10 --port 8000 --workers 1
```

Windows 브라우저에서 Ctrl+Shift+R로 갱신한다. 코드가 이미 포함된 브랜치에서는 별도 수정 없이 빌드·화면 확인만 수행한다.

## 화면에서 확인할 항목

1. 1366×768 및 1024×768에서 기존 완료 대화를 열어 입력칸과 실행 버튼이 바로 보이는지 확인한다.
2. 대화가 많거나 결과/증거/이벤트를 펼쳐도 입력칸이 밀리지 않고 대화 영역만 스크롤되는지 확인한다.
3. 입력을 여러 줄로 늘리면 입력칸이 커지고, 지우면 원래 높이로 돌아오는지 확인한다. 상한 이후에는 입력칸 안에서 스크롤되어야 한다.
4. 390×844에서도 설정 선택기, 입력칸과 버튼을 사용할 수 있는지 확인한다. 창 크기 변경 시 입력 높이도 갱신되어야 한다.
5. 토큰 로그인, 대화 전환, 결과 새로고침과 기존 로그/HTTP 시나리오 선택을 확인한다. 레이아웃 확인을 위해 OpenAI를 다시 호출할 필요는 없다.

이 문서의 미검증 항목은 실제 화면 확인 뒤에만 결과와 환경을 추가한다. 이번 레이아웃 수정에 맞춰 보안 검증 결과나 기존 run 파일을 덮어쓰지 않는다.
