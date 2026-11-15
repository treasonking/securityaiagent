import test from 'node:test';
import assert from 'node:assert/strict';
import { canExecute, statusLabel, terminal } from '../src/operator-state.js';

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
