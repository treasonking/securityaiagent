import type { Evidence, Message, RunState } from "./api";

export type TerminalRunSnapshot = {
  state: RunState;
  evidence: Evidence[];
  messages: Message[];
};

export function refreshRunState(options: {
  runId: string;
  conversationId: string | null;
  getRun: (runId: string) => Promise<RunState>;
  getEvidence: (runId: string) => Promise<Evidence[]>;
  listMessages: (conversationId: string) => Promise<Message[]>;
  isCurrent: () => boolean;
  isTerminal: (status: string) => boolean;
  commitRun: (state: RunState) => void;
  commitTerminal: (snapshot: TerminalRunSnapshot) => void;
}): Promise<"stale" | "active" | "terminal">;
