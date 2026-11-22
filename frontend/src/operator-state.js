export const terminal = new Set(['COMPLETED', 'FAILED', 'REJECTED', 'CANCELLED', 'INTERRUPTED', 'TIMED_OUT']);
export const statusLabel = (status) => ({ QUEUED:'대기', RUNNING:'실행 중', COMPLETED:'완료', FAILED:'실패', REJECTED:'실행 전 거절', CANCELLED:'중단', INTERRUPTED:'중단', TIMED_OUT:'시간 초과' })[status] || status;
export function canExecute({plan, confirmed, busy, uncertain, now}) {
  return Boolean(plan && confirmed && !busy && !uncertain && !plan.job && now < plan.expires_at * 1000);
}

// A successful listing is required before the stored selection can be discarded.
export function restoreSavedSelection(runs, storage, open) {
  const id = storage.getItem('operator-run');
  if (id === null) return;
  if (runs.some(run => run.run_id === id)) return open(id);
  storage.removeItem('operator-run');
}
