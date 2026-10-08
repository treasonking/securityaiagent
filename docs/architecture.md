# Architecture

```mermaid
flowchart LR
  UI[React static UI] -->|same-origin /api| C[Controller FastAPI]
  C --> DB[(Controller SQLite)]
  C --> P[Mock or OpenAI provider]
  C -->|function API or SDK-managed MCP| W[Worker ToolService]
  W -->|exact HTTP origin| T[Synthetic target]
  T --> TDB[(Target SQLite)]
  V[Offline verifier] -. approved local read .-> TDB
  V -. sanitized evidence .-> DB
```

## Components

- `controller/`: provider boundary, deterministic scenario runner, FastAPI API, local session/CSRF, SQLite repository, SSE job manager, report writer.
- `worker/`: one shared `ToolService` exposed by authenticated function endpoints and Streamable HTTP MCP. Both transports share policy, limits, cancellation, and evidence redaction.
- `target/`: synthetic business site with scrypt-hashed accounts, sessions, per-user documents, vulnerable/fixed authorization branch, and target-local observations.
- `verifier/`: deterministic oracle. It is not registered as an agent tool.
- `frontend/`: same-origin React client. It does not receive worker credentials or render raw HTML.

## Run sequence

```mermaid
sequenceDiagram
  participant U as User
  participant C as Controller
  participant W as Worker
  participant T as Target
  participant V as Verifier
  U->>C: registered target + scenario
  C->>C: redact/store message, queue run
  C->>W: start A/B/admin opaque sessions
  W->>T: fixed login requests
  C->>W: list own fixture IDs
  C->>W: safe controls + cross-account fetch + missing ID
  W->>T: exact-origin HTTP, no redirects
  W-->>C: marker/status/hash evidence only
  C->>V: evidence metadata
  V-->>C: VULNERABLE / BLOCKED / INCONCLUSIVE
  C-->>U: persisted SSE + report
```

모델은 후보만 제시한다. published procedure의 실행 순서와 확정 판정은 controller/verifier 코드가 소유한다.
