import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { CurrentVerdict, ResultHeading, SavedRunButton } from '../src/current-verdict.js';

for (const [state, label, reason_code] of [
  ['consistent', 'VULNERABLE', 'CROSS_ACCOUNT_PRIVATE_PROOF'],
  ['consistent', 'BLOCKED_BY_ACCESS_CONTROL', 'EXPLICIT_DENIAL_WITH_STABLE_CONTROLS'],
  ['withheld', '판정 보류 / 증거 불일치', 'REPORT_CONTRACT_MISMATCH'],
  ['withheld', '판정 보류 / 증거 불일치', 'VERDICT_MISMATCH'],
  ['unavailable', '검증 불가', 'SAVED_INPUT_UNREADABLE'],
]) {
  test(`saved conclusion renders ${reason_code}`, () => {
    const run = { run_id: 'run_test', transport: 'function', status: 'COMPLETED',
      verdict: 'VULNERABLE', conclusion: { state, label, reason_code } };
    for (const component of [SavedRunButton, ResultHeading]) {
      const html = renderToStaticMarkup(createElement(component, { run }));
      assert.ok(html.includes(label) && html.includes(reason_code));
      if (state !== 'consistent') assert.doesNotMatch(html, /VULNERABLE|BLOCKED_BY_ACCESS_CONTROL/);
    }
  });
}

test('old server response without a current conclusion cannot display a definitive verdict', () => {
  const html = renderToStaticMarkup(createElement(CurrentVerdict, { verdict: 'VULNERABLE' }));
  assert.match(html, /검증 불가/);
  assert.doesNotMatch(html, /VULNERABLE/);
});
