import test from 'node:test';
import assert from 'node:assert/strict';
import { canExecute, restoreSavedSelection, statusLabel, terminal } from '../src/operator-state.js';

test('explicit current plan approval required; uncertain/used/expired requests cannot resubmit',()=>{
  const plan={expires_at:100,job:null};
  const args={plan,confirmed:true,busy:false,uncertain:false,now:1000};
  assert.equal(canExecute(args),true);
  for(const changed of [{plan:null},{confirmed:false},{busy:true},{uncertain:true},{now:100000},{plan:{...plan,job:{status:'FAILED'}}}]) {
    assert.equal(canExecute({...args,...changed}),false);
  }
});
test('execution lifecycle is independent of security verdict',()=>{
  assert.equal(statusLabel('REJECTED'),'실행 전 거절');
  assert.equal(terminal.has('VULNERABLE'),false);
  assert.equal(terminal.has('INTERRUPTED'),true);
});

function savedSelection(id) {
  const entries = new Map([['operator-run', id], ['operator-plan', 'keep']]);
  return { getItem: key => entries.get(key) ?? null, removeItem: key => entries.delete(key) };
}

const examples = [{run_id: 'vulnerable'}, {run_id: 'blocked'}];

test('restore reads only the selected run from the current list', async () => {
  const storage = savedSelection('blocked');
  const reads = [];
  await restoreSavedSelection(examples, storage, id => reads.push(id));
  assert.deepEqual(reads, ['blocked']);
  assert.equal(storage.getItem('operator-run'), 'blocked');
});

test('stale selection is cleared without opening any detail or selecting a fallback', () => {
  const storage = savedSelection('gone');
  restoreSavedSelection(examples, storage, () => assert.fail('unexpected detail request'));
  assert.equal(storage.getItem('operator-run'), null);
  assert.equal(storage.getItem('operator-plan'), 'keep');
});

test('a detail failure preserves the selection and does not automatically retry', async () => {
  const storage = savedSelection('vulnerable');
  const reads = [];
  await assert.rejects(restoreSavedSelection(examples, storage, async id => {
    reads.push(id);
    throw new Error('temporary');
  }), /temporary/);
  assert.equal(storage.getItem('operator-run'), 'vulnerable');
  assert.deepEqual(reads, ['vulnerable']);
});
