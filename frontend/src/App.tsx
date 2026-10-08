import { useEffect, useMemo, useState } from "react";
import {
  authenticateSession,
  cancelRun,
  createConversation,
  getConfig,
  getEventLog,
  getEvidence,
  getRun,
  listConversations,
  listMessages,
  listRuns,
  logoutSession,
  restoreSession,
  submitMessage,
  type AppConfig,
  type Conversation,
  type Evidence,
  type Message,
  type RunState,
} from "./api";

const terminal = new Set(["COMPLETED", "CANCELLED", "TIMED_OUT", "FAILED", "INTERRUPTED"]);
const streamEvents = [
  "queued", "running", "tool_started", "tool_finished", "evidence_added",
  "report_ready", "cancelled", "timed_out", "failed", "offline_verification_imported",
];

export default function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [accessToken, setAccessToken] = useState("");
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [message, setMessage] = useState("취약/수정 모드의 접근 통제 시나리오를 검증해줘.");
  const [transport, setTransport] = useState<"function" | "mcp">("function");
  const [provider, setProvider] = useState<"mock" | "openai">("mock");
  const [run, setRun] = useState<RunState | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [error, setError] = useState("");
  const busy = useMemo(() => Boolean(run && !terminal.has(run.status)), [run]);

  async function loadWorkspace() {
    const [nextConfig, nextConversations] = await Promise.all([getConfig(), listConversations()]);
    setConfig(nextConfig);
    setConversations(nextConversations);
    setActiveConversation((current) => current ?? nextConversations[0]?.conversation_id ?? null);
  }

  useEffect(() => {
    restoreSession()
      .then(async () => {
        setAuthenticated(true);
        await loadWorkspace();
      })
      .catch(() => setAuthenticated(false));
  }, []);

  useEffect(() => {
    if (!authenticated || !activeConversation) return;
    let disposed = false;
    setRun(null);
    setEvidence([]);
    setEvents([]);
    Promise.all([listMessages(activeConversation), listRuns(activeConversation)])
      .then(async ([nextMessages, runs]) => {
        if (disposed) return;
        setMessages(nextMessages);
        const latest = runs[0] ?? null;
        setRun(latest);
        if (latest) {
          const [nextEvidence, log] = await Promise.all([
            getEvidence(latest.run_id), getEventLog(latest.run_id),
          ]);
          if (!disposed) {
            setEvidence(nextEvidence);
            setEvents(log.map((item) => `${item.event_id}:${item.event_type}: ${JSON.stringify(item.payload)}`));
          }
        }
      })
      .catch((cause: Error) => !disposed && setError(cause.message));
    return () => { disposed = true; };
  }, [authenticated, activeConversation]);

  useEffect(() => {
    if (!run || terminal.has(run.status)) return;
    const runId = run.run_id;
    const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);
    let pollTimer: number | undefined;

    async function refreshRun() {
      const state = await getRun(runId);
      setRun((current) => current?.run_id === runId ? state : current);
      if (terminal.has(state.status)) {
        setEvidence(await getEvidence(runId));
        if (activeConversation) setMessages(await listMessages(activeConversation));
        source.close();
        if (pollTimer) window.clearInterval(pollTimer);
      }
    }

    for (const type of streamEvents) {
      source.addEventListener(type, (event) => {
        if (!(event instanceof MessageEvent)) return;
        const key = `${event.lastEventId || "0"}:${type}`;
        setEvents((current) => current.some((item) => item.startsWith(`${key}:`))
          ? current
          : [...current, `${key}: ${event.data}`]);
        if (["report_ready", "cancelled", "timed_out", "failed", "offline_verification_imported"].includes(type)) {
          void refreshRun().catch((cause: Error) => setError(cause.message));
        }
      });
    }
    source.onerror = () => {
      if (!pollTimer) {
        pollTimer = window.setInterval(() => {
          void refreshRun().catch((cause: Error) => setError(cause.message));
        }, 1000);
      }
    };
    return () => {
      source.close();
      if (pollTimer) window.clearInterval(pollTimer);
    };
  }, [run?.run_id, run?.status, activeConversation]);

  async function login() {
    try {
      setError("");
      await authenticateSession(accessToken);
      setAccessToken("");
      setAuthenticated(true);
      await loadWorkspace();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "인증하지 못했습니다.");
    }
  }

  async function logout() {
    await logoutSession();
    setAuthenticated(false);
    setConversations([]);
    setActiveConversation(null);
    setRun(null);
  }

  async function newConversation() {
    const created = await createConversation();
    const next = await listConversations();
    setConversations(next);
    setActiveConversation(created.conversation_id);
  }

  async function startRun() {
    try {
      setError("");
      let conversationId = activeConversation;
      if (!conversationId) {
        const created = await createConversation();
        conversationId = created.conversation_id;
        setActiveConversation(conversationId);
        setConversations(await listConversations());
      }
      const submitted = await submitMessage(conversationId, message, transport, provider);
      setEvents(["0:queued: submitted"]);
      setEvidence([]);
      setRun(await getRun(submitted.run_id));
      setMessages(await listMessages(conversationId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "작업을 시작하지 못했습니다.");
    }
  }

  async function stopRun() {
    if (!run) return;
    await cancelRun(run.run_id);
    setRun(await getRun(run.run_id));
  }

  async function refreshCurrentRun() {
    if (!run) return;
    const runId = run.run_id;
    const [state, nextEvidence, log] = await Promise.all([
      getRun(runId), getEvidence(runId), getEventLog(runId),
    ]);
    setRun((current) => current?.run_id === runId ? state : current);
    setEvidence(nextEvidence);
    setEvents(log.map((item) => `${item.event_id}:${item.event_type}: ${JSON.stringify(item.payload)}`));
  }

  if (!authenticated) {
    return (
      <main className="login-shell">
        <section className="login-card">
          <p className="eyebrow">LOCAL ACCESS CONTROL</p>
          <h1>SecurityLab AI</h1>
          <p>서버에 설정한 초기 접근 토큰으로 인증하세요. OpenAI 키와 worker 토큰은 브라우저에 입력하지 않습니다.</p>
          {error && <p className="error" role="alert">{error}</p>}
          <input
            type="password"
            value={accessToken}
            onChange={(event) => setAccessToken(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && void login()}
            aria-label="초기 접근 토큰"
          />
          <button disabled={!accessToken} onClick={login}>인증</button>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">LOCAL EVIDENCE LAB</p>
          <h1>SecurityLab AI</h1>
          <p className="subtle">고정 시나리오 검증기 + LLM 후보 생성기</p>
        </div>
        <button className="new-button" onClick={newConversation}>+ 새 대화</button>
        <nav aria-label="대화 이력">
          {conversations.map((conversation) => (
            <button
              className={conversation.conversation_id === activeConversation ? "history active" : "history"}
              key={conversation.conversation_id}
              onClick={() => setActiveConversation(conversation.conversation_id)}
            >
              <strong>{conversation.title}</strong>
              <span>{new Date(conversation.created_at).toLocaleString()}</span>
            </button>
          ))}
        </nav>
        <button className="new-button" onClick={logout}>로그아웃</button>
        <div className="phase-note">2단계 예정: Nmap · Playwright</div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><span className="status-dot" /> 인증된 단일 사용자 · synthetic-only</div>
          <div className="scope">lab-web / access-control</div>
        </header>

        <section className="conversation" aria-live="polite">
          {messages.length === 0 && (
            <div className="empty-state">
              <p className="eyebrow">EVIDENCE BEFORE CLAIMS</p>
              <h2>접근 통제를 재현 가능한 증거로 확인하세요.</h2>
              <p>후보 판단과 verifier 확정 결과를 분리하고, 원문 HTML·쿠키·토큰은 표시하지 않습니다.</p>
            </div>
          )}
          {messages.map((item) => (
            <article className={`message ${item.role}`} key={item.message_id}>
              <span>{item.role === "user" ? "사용자" : "SecurityLab"}</span>
              <p>{item.content}</p>
            </article>
          ))}

          {run && (
            <section className="run-card">
              <div className="run-heading">
                <div><p className="eyebrow">RUN STATUS</p><h2>{run.report?.verdict ?? run.status}</h2></div>
                <div className="run-actions">
                  {!busy && <button className="refresh" onClick={refreshCurrentRun}>결과 새로고침</button>}
                  {busy && <button className="danger" onClick={stopRun}>실행 중단</button>}
                </div>
              </div>
              {run.report && (
                <>
                  <div className="result-grid">
                    <div><span>Target mode</span><strong>{run.report.mode}</strong></div>
                    <div><span>Provider</span><strong>{run.report.provider_mode}</strong></div>
                    <div><span>Transport</span><strong>{run.report.tool_transport}</strong></div>
                  </div>
                  <p className="subtle">Target log: {run.report.environment.target_server_log}</p>
                  <div className="decision-split">
                    <section><span>모델 후보 · 미확정</span>{run.report.finding_candidates.map((item) => <p key={item.finding_type}>{item.finding_type}: {item.rationale}</p>)}</section>
                    <section><span>Verifier · 증거 확정</span>{run.report.verified_findings.map((item) => <p key={item.finding_type}>{item.verdict}: {item.reason}</p>)}</section>
                  </div>
                </>
              )}
              <details><summary>정제된 기술 이벤트 ({events.length})</summary><ol className="event-list">{events.map((item) => <li key={item}>{item}</li>)}</ol></details>
              <details>
                <summary>정제된 증거 ({evidence.length})</summary>
                <div className="evidence-list">{evidence.map((item) => <article key={item.evidence_id}><strong>{item.purpose}</strong><code>{item.method} {item.path} → {item.status_code}</code><span>{item.synthetic_document_marker ?? "marker 없음"} · {item.server_observation}</span></article>)}</div>
              </details>
              {run.report?.recommendations.map((item) => <p className="recommendation" key={item}>{item}</p>)}
              {run.report?.warnings.map((item) => <p className="warning" key={item}>{item}</p>)}
            </section>
          )}
        </section>

        <footer className="composer">
          {error && <p className="error" role="alert">{error}</p>}
          <div className="controls">
            <label>대상<select disabled><option>lab-web</option></select></label>
            <label>시나리오<select disabled><option>access-control</option></select></label>
            <label>Provider<select value={provider} onChange={(event) => setProvider(event.target.value as "mock" | "openai")}><option value="mock">mock · 검증됨</option><option value="openai" disabled={!config?.providers.openai.configured}>OpenAI · {config?.providers.openai.configured ? "설정됨/미검증" : "미설정"}</option></select></label>
            <label>도구 연결<select value={transport} onChange={(event) => setTransport(event.target.value as "function" | "mcp")}><option value="function">function / worker API</option><option value="mcp">SDK-managed MCP</option></select></label>
          </div>
          <div className="input-row"><textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={3} /><button disabled={busy || !message.trim()} onClick={startRun}>검증 실행</button></div>
          <small>자유문은 실행 계획을 바꾸지 않습니다. 등록된 고정 시나리오와 도구 순서만 실행합니다.</small>
        </footer>
      </section>
    </main>
  );
}
