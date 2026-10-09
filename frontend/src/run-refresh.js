export async function refreshRunState({
  runId,
  conversationId,
  getRun,
  getEvidence,
  listMessages,
  isCurrent,
  isTerminal,
  commitRun,
  commitTerminal,
}) {
  const state = await getRun(runId);
  if (!isCurrent()) return "stale";

  if (!isTerminal(state.status)) {
    commitRun(state);
    return "active";
  }

  const [evidence, messages] = await Promise.all([
    getEvidence(runId),
    conversationId ? listMessages(conversationId) : Promise.resolve([]),
  ]);
  if (!isCurrent()) return "stale";

  commitTerminal({ state, evidence, messages });
  return "terminal";
}
