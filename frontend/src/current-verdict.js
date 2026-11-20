import { createElement as h } from 'react';
import { statusLabel } from './operator-state.js';

// Both the history button and the detail heading display the server's conclusion.
export function CurrentVerdict({ conclusion }) {
  if (!conclusion) return h('span', null, '검증 불가 · 현재 결론 미제공');
  return h('span', { className: conclusion.state === 'consistent' ? undefined : 'warning' },
    conclusion.label, ' · ', conclusion.reason_code);
}

export function SavedRunButton({ run, onOpen }) {
  return h('button', { onClick: () => onOpen(run.run_id) },
    h(CurrentVerdict, { conclusion: run.conclusion }),
    h('small', null, run.transport, ' · ', run.run_id.slice(-8)));
}

export function ResultHeading({ run }) {
  return h('div', { className: 'operator-section-heading' },
    h('strong', null, '실행: ', statusLabel(run.status)),
    h('strong', null, '현재 결론: ', h(CurrentVerdict, { conclusion: run.conclusion })));
}
