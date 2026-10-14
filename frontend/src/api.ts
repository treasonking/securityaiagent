export type Conversation = {
  conversation_id: string;
  title: string;
  created_at: string;
};

export type Message = {
  message_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

export type Evidence = {
  evidence_id: string;
  purpose: string;
  method: string;
  path: string;
  status_code: number;
  account_ref: string;
  synthetic_document_marker: string | null;
  server_observation: string;
};

export type RunReport = {
  run_id: string;
  status: string;
  verdict: "VULNERABLE" | "BLOCKED_BY_ACCESS_CONTROL" | "INCONCLUSIVE";
  mode: string;
  provider_mode: string;
  tool_transport: string;
  environment: Record<string, string>;
  finding_candidates: Array<{ finding_type: "cross_account_document_access"; rationale: string; source: string }>;
  verified_findings: Array<{ finding_type: string; verdict: string; reason: string }>;
  warnings: string[];
  recommendations: string[];
};

export type RunState = {
  run_id: string;
  status: string;
  tool_transport: string;
  report: RunReport | null;
};

export type AppConfig = {
  workflow: string;
  providers: Record<"mock" | "openai", { configured: boolean; verified: boolean }>;
  transports: string[];
};

export type RunEvent = {
  run_id: string;
  event_id: number;
  event_type: string;
  payload: Record<string, unknown>;
};

let csrfToken = "";

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`${response.status}: ${message}`);
  }
  return response.json() as Promise<T>;
}

export async function authenticateSession(accessToken: string): Promise<void> {
  const response = await fetch("/api/session", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_token: accessToken }),
  });
  const data = await parse<{ csrf_token: string }>(response);
  csrfToken = data.csrf_token;
}

export async function restoreSession(): Promise<void> {
  const response = await fetch("/api/session", { credentials: "same-origin" });
  const data = await parse<{ csrf_token: string }>(response);
  csrfToken = data.csrf_token;
}

export async function logoutSession(): Promise<void> {
  const response = await fetch("/api/session", {
    method: "DELETE",
    credentials: "same-origin",
    headers: writeHeaders(),
  });
  await parse(response);
  csrfToken = "";
}

function writeHeaders(): HeadersInit {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrfToken };
}

export async function getConfig(): Promise<AppConfig> {
  const response = await fetch("/api/config", { credentials: "same-origin" });
  return parse<AppConfig>(response);
}

export async function listConversations(): Promise<Conversation[]> {
  const response = await fetch("/api/conversations", { credentials: "same-origin" });
  return (await parse<{ conversations: Conversation[] }>(response)).conversations;
}

export async function createConversation(): Promise<Conversation> {
  const response = await fetch("/api/conversations", {
    method: "POST",
    credentials: "same-origin",
    headers: writeHeaders(),
    body: JSON.stringify({ title: "접근 통제 검증" }),
  });
  return parse<Conversation>(response);
}

export async function listMessages(conversationId: string): Promise<Message[]> {
  const response = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}/messages`, {
    credentials: "same-origin",
  });
  return (await parse<{ messages: Message[] }>(response)).messages;
}

export async function listRuns(conversationId: string): Promise<RunState[]> {
  const response = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}/runs`, {
    credentials: "same-origin",
  });
  return (await parse<{ runs: RunState[] }>(response)).runs;
}

export async function submitMessage(
  conversationId: string,
  message: string,
  transport: "function" | "mcp",
  provider: "mock" | "openai",
): Promise<{ run_id: string }> {
  const response = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: "POST",
    credentials: "same-origin",
    headers: writeHeaders(),
    body: JSON.stringify({
      message,
      scenario_id: "access-control",
      target_id: "lab-web",
      provider,
      tool_transport: transport,
    }),
  });
  return parse<{ run_id: string }>(response);
}

export async function getRun(runId: string): Promise<RunState> {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { credentials: "same-origin" });
  return parse<RunState>(response);
}

export async function getEvidence(runId: string): Promise<Evidence[]> {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/evidence`, {
    credentials: "same-origin",
  });
  return (await parse<{ evidence: Evidence[] }>(response)).evidence;
}

export async function getEventLog(runId: string): Promise<RunEvent[]> {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/event-log`, {
    credentials: "same-origin",
  });
  return (await parse<{ events: RunEvent[] }>(response)).events;
}

export async function cancelRun(runId: string): Promise<void> {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
    credentials: "same-origin",
    headers: writeHeaders(),
    body: "{}",
  });
  await parse(response);
}
