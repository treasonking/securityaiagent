import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");

test("React UI never enables raw HTML rendering", () => {
  assert.equal(app.includes("dangerouslySetInnerHTML"), false);
});

test("browser only calls same-origin controller API", () => {
  assert.equal(api.includes("http://"), false);
  assert.equal(api.includes("https://"), false);
  assert.match(api, /credentials: "same-origin"/);
});

test("API key and worker token are not UI fields", () => {
  assert.equal(app.includes("OPENAI_API_KEY"), false);
  assert.equal(app.includes("WORKER_TOKEN"), false);
});

test("UI requires an explicit local access token before workspace calls", () => {
  assert.match(app, /authenticateSession\(accessToken\)/);
  assert.match(api, /method: "POST"[\s\S]*access_token: accessToken/);
  assert.match(app, /type="password"/);
});

test("provider selection is server-configured and never falls back silently", () => {
  assert.match(api, /getConfig/);
  assert.match(app, /providers\.openai\.configured/);
  assert.match(api, /provider,/);
});

test("empty model candidates remain distinct from the verifier verdict", () => {
  assert.match(app, /finding_candidates\.length === 0/);
  assert.match(app, /모델 후보 없음 · 접근 통제 판정은 별도 증거 기반입니다\./);
  assert.match(app, /Verifier · 증거 확정/);
});

test("conversation changes restore runs, evidence, and event history", () => {
  assert.match(api, /listRuns/);
  assert.match(api, /getEventLog/);
  assert.match(app, /Promise\.all\(\[listMessages\(conversationId\), listRuns\(conversationId\)\]\)/);
  assert.match(app, /activeConversationRef\.current !== conversationId/);
  assert.match(app, /activeRunRef\.current !== runId/);
  assert.match(app, /async function refreshCurrentRun\(\)[\s\S]*activeRunRef\.current !== runId/);
  assert.match(app, /refreshRunState\(\{/);
  assert.match(app, /commitTerminal: \(\{ state, evidence: nextEvidence, messages: nextMessages \}\)/);
});

test("SSE lifecycle cleans up and uses polling fallback", () => {
  assert.match(app, /source\.close\(\)/);
  assert.match(app, /window\.setInterval/);
  assert.equal(app.includes("source.onerror = () => source.close()"), false);
});

test("completed runs can refresh an imported offline verdict", () => {
  assert.match(app, /refreshCurrentRun/);
  assert.match(app, /결과 새로고침/);
  assert.match(app, /offline_verification_imported/);
});
