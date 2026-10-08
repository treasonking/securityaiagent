import { useEffect, useMemo, useState } from "react";
import {
  cancelRun,
  createConversation,
  getEvidence,
  getRun,
  initializeSession,
  listConversations,
  listMessages,
  submitMessage,
  type Conversation,
  type Evidence,
  type Message,
  type RunState,
} from "./api";

const terminal = new Set(["COMPLETED", "CANCELLED", "FAILED", "INTERRUPTED"]);

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [message, setMessage] = useState("취약/수정 모드의 접근 통제 시나리오를 검증해줘.");
  const [transport, setTransport] = useState<"function" | "mcp">("function");
  const [run, setRun] = useState<RunState | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [error, setError] = useState("");
  const busy = useMemo(() => Boolean(run && !terminal.has(run.status)), [run]);

  async function refreshConversations() {
    const next = await listConversations();
    setConversations(next);
    if (!activeConversation && next.length) setActiveConversation(next[0].conversation_id);
  }

  useEffect(() => {
    initializeSession().then(refreshConversations).catch((cause: Error) => setError(cause.message));
  }, []);

  useEffect(() => {
    if (!activeConversation) return;
    listMessages(activeConversation).then(setMessages).catch((cause: Error) => setError(cause.message));
  }, [activeConversation]);

  async function newConversation() {
    const created = await createConversation();
    await refreshConversations();
    setActiveConversation(created.conversation_id);
    setMessages([]);
    setRun(null);
    setEvidence([]);
    setEvents([]);
  }

  async function startRun() {
    try {
      setError("");
      let conversationId = activeConversation;
      if (!conversationId) {
        const created = await createConversation();
        conversationId = created.conversation_id;
        setActiveConversation(conversationId);
        await refreshConversations();
      }
      const submitted = await submitMessage(conversationId, message, transport);
      setEvents(["queued"]);
      const source = new EventSource(`/api/runs/${encodeURIComponent(submitted.run_id)}/events`);
      const knownEvents = [
        "queued",
        "running",
        "tool_started",
        "tool_finished",
        "evidence_added",
        "report_ready",
        "cancelled",
        "failed",
      ];
      for (const type of knownEvents) {
        source.addEventListener(type, async (event) => {
          const detail = JSON.parse((event as MessageEvent).data) as Record<string, unknown>;
          setEvents((current) => [...current, `${type}: ${JSON.stringify(detail)}`]);
          if (["report_ready", "cancelled", "failed"].includes(type)) {
            source.close();
            const state = await getRun(submitted.run_id);
            setRun(state);
            setEvidence(await getEvidence(submitted.run_id));
            setMessages(await listMessages(conversationId!));
          }
        });
      }
      source.onerror = () => source.close();
      setRun(await getRun(submitted.run_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "작업을 시작하지 못했습니다.");
    }
  }

  async function stopRun() {
    if (!run) return;
    await cancelRun(run.run_id);
    setRun(await getRun(run.run_id));
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">LOCAL EVIDENCE LAB</p>
          <h1>SecurityLab AI</h1>
          <p className="subtle">등록된 합성 대상만 검증합니다.</p>
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
        <div className="phase-note">2단계 예정: Nmap · Playwright</div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><span className="status-dot" /> 단일 사용자 · synthetic-only</div>
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
                <div>
                  <p className="eyebrow">RUN STATUS</p>
                  <h2>{run.report?.verdict ?? run.status}</h2>
                </div>
                {busy && <button className="danger" onClick={stopRun}>실행 중단</button>}
              </div>
              {run.report && (
                <>
                  <div className="result-grid">
                    <div><span>Target mode</span><strong>{run.report.mode}</strong></div>
                    <div><span>Provider</span><strong>{run.report.provider_mode}</strong></div>
                    <div><span>Transport</span><strong>{run.report.tool_transport}</strong></div>
                  </div>
                  <div className="decision-split">
                    <section>
                      <span>모델 후보 · 미확정</span>
                      {run.report.finding_candidates.map((item) => <p key={item.finding_type}>{item.finding_type}: {item.rationale}</p>)}
                    </section>
                    <section>
                      <span>Verifier · 증거 확정</span>
                      {run.report.verified_findings.map((item) => <p key={item.finding_type}>{item.verdict}: {item.reason}</p>)}
                    </section>
                  </div>
                </>
              )}
              <details>
                <summary>정제된 기술 이벤트 ({events.length})</summary>
                <ol className="event-list">{events.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ol>
              </details>
              <details>
                <summary>정제된 증거 ({evidence.length})</summary>
                <div className="evidence-list">
                  {evidence.map((item) => (
                    <article key={item.evidence_id}>
                      <strong>{item.purpose}</strong>
                      <code>{item.method} {item.path} → {item.status_code}</code>
                      <span>{item.synthetic_document_marker ?? "marker 없음"} · {item.server_observation}</span>
                    </article>
                  ))}
                </div>
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
            <label>도구 연결<select value={transport} onChange={(event) => setTransport(event.target.value as "function" | "mcp")}><option value="function">function / worker API</option><option value="mcp">SDK-managed MCP</option></select></label>
          </div>
          <div className="input-row">
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={3} />
            <button disabled={busy || !message.trim()} onClick={startRun}>검증 실행</button>
          </div>
          <small>입력한 URL은 대상 등록이나 정책 변경으로 해석되지 않습니다.</small>
        </footer>
      </section>
    </main>
  );
}
