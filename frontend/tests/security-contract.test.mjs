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
