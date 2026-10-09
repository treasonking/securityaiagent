import assert from "node:assert/strict";
import test from "node:test";

import { refreshRunState } from "../src/run-refresh.js";

function deferred() {
  let resolve;
  const promise = new Promise((next) => { resolve = next; });
  return { promise, resolve };
}

const terminalState = {
  run_id: "run-a",
  status: "COMPLETED",
  tool_transport: "function",
  report: { verdict: "VULNERABLE" },
};

test("delayed terminal details publish run, evidence, and messages together", async () => {
  const delayedEvidence = deferred();
  const delayedMessages = deferred();
  const commits = [];
  const requested = { evidence: false, messages: false };

  const refresh = refreshRunState({
    runId: "run-a",
    conversationId: "conv-a",
    getRun: async () => terminalState,
    getEvidence: () => {
      requested.evidence = true;
      return delayedEvidence.promise;
    },
    listMessages: () => {
      requested.messages = true;
      return delayedMessages.promise;
    },
    isCurrent: () => true,
    isTerminal: (status) => status === "COMPLETED",
    commitRun: (state) => commits.push({ kind: "run", state }),
    commitTerminal: (snapshot) => commits.push({ kind: "terminal", ...snapshot }),
  });

  await Promise.resolve();
  assert.deepEqual(requested, { evidence: true, messages: true });
  assert.deepEqual(commits, [], "terminal run must wait for its detail snapshot");
  delayedEvidence.resolve([{ evidence_id: "ev-a" }]);
  await Promise.resolve();
  assert.deepEqual(commits, [], "one delayed detail response must not publish partial state");
  delayedMessages.resolve([{ message_id: "msg-a", content: "완료" }]);

  assert.equal(await refresh, "terminal");
  assert.equal(commits.length, 1);
  assert.equal(commits[0].kind, "terminal");
  assert.equal(commits[0].state.report.verdict, "VULNERABLE");
  assert.deepEqual(commits[0].evidence, [{ evidence_id: "ev-a" }]);
  assert.deepEqual(commits[0].messages, [{ message_id: "msg-a", content: "완료" }]);
});

test("delayed terminal details are discarded after conversation changes", async () => {
  const delayedEvidence = deferred();
  const delayedMessages = deferred();
  const selection = { conversationId: "conv-a", runId: "run-a", disposed: false };
  const commits = [];
  const requested = { evidence: false, messages: false };

  const refresh = refreshRunState({
    runId: "run-a",
    conversationId: "conv-a",
    getRun: async () => terminalState,
    getEvidence: () => {
      requested.evidence = true;
      return delayedEvidence.promise;
    },
    listMessages: () => {
      requested.messages = true;
      return delayedMessages.promise;
    },
    isCurrent: () => (
      !selection.disposed
      && selection.conversationId === "conv-a"
      && selection.runId === "run-a"
    ),
    isTerminal: (status) => status === "COMPLETED",
    commitRun: (state) => commits.push({ kind: "run", state }),
    commitTerminal: (snapshot) => commits.push({ kind: "terminal", ...snapshot }),
  });

  await Promise.resolve();
  assert.deepEqual(requested, { evidence: true, messages: true });
  selection.conversationId = "conv-b";
  selection.runId = "run-b";
  selection.disposed = true;
  delayedEvidence.resolve([{ evidence_id: "stale-ev" }]);
  delayedMessages.resolve([{ message_id: "stale-msg", content: "오래된 응답" }]);

  assert.equal(await refresh, "stale");
  assert.deepEqual(commits, [], "stale terminal responses must not update the new conversation");
});
