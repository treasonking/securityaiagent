import { useEffect, useRef, useState } from 'react';
import { ResultHeading, SavedRunButton } from './current-verdict.js';
import DisclosureDraft from './DisclosureDraft';
import * as api from './operator-api';
import { canExecute, statusLabel, terminal } from './operator-state.js';

function Policy({ value }: { value: api.Policy }) {
  const s = value.scope_policy;
  return <section className="operator-policy">
    <h3>{value.target_id} <small>{value.auth_mode} · mock</small></h3>
    <p className="mono">{value.origin}</p>
    <p>{value.scenario_id} / {value.contract_version}</p>
    <div className="operator-facts">{value.accounts.map(a => <div key={a.alias}><strong>{a.alias}</strong><span>{a.resource_id}</span></div>)}</div>
    <p>정책 {s.profile_id} · revision {s.revision}</p><code className="operator-digest">{s.snapshot_sha256}</code>
    <dl className="operator-limits">{Object.entries(s.effective_limits).map(([key, n]) => <div key={key}><dt>{key}</dt><dd>{n}</dd></div>)}</dl>
    {s.tls ? <details><summary>HTTPS 검증 방식 · CA fingerprint</summary><pre>{JSON.stringify(s.tls,null,2)}</pre></details> : <p>등록된 HTTP 대상 · TLS 해당 없음</p>}
    {s.domain && <div><strong>승인 IP/CIDR</strong><p>{s.domain.allowed_ip_ranges.join(', ')}</p><small>DNS 전체 결과 검사 · 검증한 IP로 연결 고정 · 비공인 주소 허용: {s.domain.allow_non_global ? '명시적 허용' : '거절'}</small></div>}
  </section>;
}

export default function OperatorWorkspace({ onChat, onLogout }: { onChat: () => void; onLogout: () => void }) {
  const [profiles,setProfiles] = useState<api.Profile[]>([]);
  const [selected,setSelected] = useState('');
  const [transport,setTransport] = useState('function');
  const [plan,setPlan] = useState<api.Plan | null>(null);
  const [confirmed,setConfirmed] = useState(false);
  const [busy,setBusy] = useState(false);
  const [uncertain,setUncertain] = useState(false);
  const [result,setResult] = useState<api.Result | null>(null);
  const [jobs,setJobs] = useState<api.Job[]>([]);
  const [runs,setRuns] = useState<api.PastRun[]>([]);
  const [error,setError] = useState('');
  const [refreshError,setRefreshError] = useState('');
  const [notice,setNotice] = useState('');
  const [now,setNow] = useState(Date.now());
  const active = useRef('');
  const activePlan = useRef('');
  const planIdentity = useRef('');
  const inFlight = useRef(false);
  const profile = profiles.find(p => p.profile_id === selected);

  async function history() {
    const [j,r] = await Promise.all([api.jobs(),api.runs()]);
    setJobs(j.jobs); setRuns(r.runs);
  }
  async function openResult(id: string) {
    active.current=id;
    setResult(null);
    sessionStorage.setItem('operator-run',id);
    try { const r=await api.result(id); if(active.current===id) { setResult(r);setRefreshError(''); } }
    catch (cause) {
      if (active.current !== id) return;
      setResult(null);
      if (cause instanceof api.OperatorError && cause.code === 'SAVED_INPUT_UNREADABLE') {
        setRefreshError(cause.message);
        await history().catch(() => setRuns([]));
      } else {
        setRefreshError('결과 갱신에 실패했습니다. 기존 상태를 다시 조회하세요.');
      }
    }
  }
  function acceptPlan(next: api.Plan) {
    const identity=next.plan_id+next.plan_sha256;
    if(planIdentity.current!==identity) setConfirmed(false);
    planIdentity.current=identity;setPlan(next);setSelected(next.profile_id);setTransport(next.transport);
  }
  async function recover(id = plan?.plan_id, select = false) {
    if(!id) { await history(); return; }
    if(select) { activePlan.current=id;setConfirmed(false);sessionStorage.setItem('operator-plan',id); }
    try {
      const next=await api.getPlan(id);
      if(activePlan.current!==id) return;
      acceptPlan(next);setRefreshError('');
      if(next.job?.run_id && terminal.has(next.job.status)) await openResult(next.job.run_id);
      await history();
    } catch { setRefreshError('상태 조회에 실패했습니다. 실행 여부가 불확실하므로 자동 재실행하지 않습니다.'); }
  }
  useEffect(() => {
    let live=true;
    api.profiles().then(async value => {
      if(!live) return;
      setProfiles(value.profiles);setSelected(value.profiles[0]?.profile_id || '');setNotice(value.message || '');
      if(value.configured) {
        await history();
        const previous=sessionStorage.getItem('operator-plan');
        if(previous) await recover(previous,true);
        else { const run=sessionStorage.getItem('operator-run'); if(run) await openResult(run); }
      }
    }).catch(() => live && setError('준비 상태를 조회하지 못했습니다. 인증과 Controller 연결을 확인하세요.'));
    const clock=window.setInterval(() => setNow(Date.now()),1000);
    return () => { live=false;window.clearInterval(clock);active.current='';activePlan.current=''; };
  },[]);
  useEffect(() => {
    if(!plan?.job || terminal.has(plan.job.status)) return;
    const id=plan.plan_id;
    const timer=window.setInterval(() => { void recover(id); },1200);
    return () => window.clearInterval(timer);
  },[plan?.plan_id,plan?.job?.status]);

  async function makePreview() {
    if(inFlight.current) return;
    inFlight.current=true;setBusy(true);setConfirmed(false);setError('');setUncertain(false);setResult(null);active.current='';activePlan.current='';
    try { const p=await api.preview(selected,transport);activePlan.current=p.plan_id;acceptPlan(p);sessionStorage.setItem('operator-plan',p.plan_id); }
    catch(cause) { setPlan(null);setError(cause instanceof Error ? cause.message : 'preview 실패'); }
    finally { inFlight.current=false;setBusy(false); }
  }
  async function run() {
    if(inFlight.current || !canExecute({plan,confirmed,busy,uncertain,now}) || !plan) return;
    inFlight.current=true;setBusy(true);setError('');
    const current=plan;
    try { const job=await api.execute(current);setPlan({...current,job});setConfirmed(false);await history(); }
    catch(cause) { setUncertain(true);setConfirmed(false);setError((cause instanceof Error ? cause.message : '응답을 받지 못했습니다.')+' 기존 상태를 조회하세요. 자동 재실행하지 않습니다.'); }
    finally { inFlight.current=false;setBusy(false); }
  }

  return <main className="operator-shell">
    <header className="operator-header"><div><p className="eyebrow">OPERATOR WORKSPACE</p><h1>검사 워크스페이스</h1><p>등록 프로필 → 계획 확인 → 실행 → 근거와 재현 보고서</p></div><nav><button onClick={onChat}>기존 시나리오·채팅</button><button onClick={onLogout}>로그아웃</button></nav></header>
    <div className="operator-body">
      <aside className="operator-sidebar"><h2>등록 대상</h2><label>준비된 프로필<select aria-label="검사 프로필" value={selected} disabled={busy} onChange={e=>{setSelected(e.target.value);activePlan.current="";sessionStorage.removeItem("operator-plan");setPlan(null);setConfirmed(false);setUncertain(false);}}>{profiles.map(p=><option key={p.profile_id} value={p.profile_id}>{p.name}</option>)}</select></label>
        <label>연결 방식<select aria-label="연결 방식" value={transport} disabled={busy} onChange={e=>{setTransport(e.target.value);activePlan.current="";sessionStorage.removeItem("operator-plan");setPlan(null);setConfirmed(false);setUncertain(false);}}><option value="function">function</option><option value="mcp">MCP</option></select></label>
        <p className="operator-note">서버 측 등록만 허용합니다. 준비 상태 조회는 Worker 정책 조회이며 Target 로그인·접속 성공 확인이 아닙니다.</p>
        {notice && <p>{notice}</p>}{profile && <p className={profile.ready?'operator-ready':'error'}>{profile.ready?'설정 준비됨 · Target 미접속':profile.message}</p>}
        <h2>최근 제출</h2><div className="operator-history">{jobs.map(j=><button key={j.plan_id} disabled={busy} onClick={()=>{setConfirmed(false);void recover(j.plan_id,true);}}>{statusLabel(j.status)} · {j.plan_id.slice(-8)}<small>{j.run_id?.slice(-8) || '실행 전'}</small></button>)}</div>
        <h2>저장된 검사</h2><div className="operator-history">{runs.map(r=><SavedRunButton key={r.run_id} run={r} onOpen={openResult}/>)}</div>
      </aside>
      <section className="operator-content" aria-label="계획과 결과">
        {error && <p className="error" role="alert">{error}</p>}{refreshError && <p className="warning" role="alert">{refreshError}</p>}
        {!plan && profile?.policy && <><h2>준비 상태와 적용 정책</h2><Policy value={profile.policy}/></>}
        {plan && <section><div className="operator-section-heading"><h2>계획 검토</h2><span>{plan.transport} · mock · 예상 HTTP {plan.expected_http_requests} / 도구 {plan.expected_tool_calls}</span></div>
          <p>{plan.plan_id}</p><p>만료: {new Date(plan.expires_at*1000).toLocaleString()} {now>=plan.expires_at*1000 && '· 만료됨'}</p><code className="operator-digest">{plan.plan_sha256}</code>
          <Policy value={plan.policy}/><h3>수행할 요청 순서</h3><ol className="operator-sequence">{plan.sequence.map(s=><li key={s.index}><strong>{s.account_ref}</strong> · {s.operation} <code>{s.method} {s.path}</code></li>)}</ol><p>{plan.interpretation}</p>
          {plan.job && <div className="operator-job" role="status"><strong>실행 상태: {statusLabel(plan.job.status)}</strong><p>{plan.job.run_id || '아직 run이 생성되지 않았습니다.'}</p>{plan.job.message && <p>{plan.job.message}</p>}</div>}
        </section>}
        {result && <section className="operator-result"><h2>저장된 검사 결과</h2><ResultHeading run={result}/><p>{result.run_id} · {result.transport}</p>{result.conclusion?.state === 'consistent' && result.message && <p>{result.message}</p>}
          <p>실제 Worker 사용량: HTTP {result.usage.http_requests} / 도구 {result.usage.tool_calls} · 설정 최대: HTTP {result.policy.scope_policy.effective_limits.max_requests} / 도구 {result.policy.scope_policy.effective_limits.max_tool_calls}</p><p>모델 후보 없음 · 고정 mock 실행 · HTTP 증거 기반 판정</p>
          <p>최초 판정(이력): {result.verdict} · {result.reason_code}</p><p>저장 증거 재판정: {result.replay.verdict} · {result.replay.reason_code} · {result.replay.verdict_matches?'최초 판정과 일치':'불일치 — 기록 검토 필요'}</p><p className="operator-note">이번 두 계정·두 리소스의 관측 범위에 한정됩니다. INCONCLUSIVE는 안전 판정이 아닙니다.</p>
          <div className="operator-downloads"><a href={api.downloadUrl(result.run_id,'markdown')}>Markdown 보고서 다운로드</a><a href={api.downloadUrl(result.run_id,'json')}>JSON 보고서 다운로드</a></div>
          <DisclosureDraft key={result.run_id} run={result}/>
          <details><summary>HTTP 증거 ({result.evidence.length})</summary><div className="operator-detail-scroll">{result.evidence.map(e=><article key={e.evidence_id}><code>{e.evidence_id}</code><p>{e.account_ref} · {e.method} {e.path} → {e.status_code}</p><small>{e.reason_code}</small></article>)}</div></details>
          <details><summary>DNS/TLS 연결 관측 ({result.connections.length})</summary><pre className="operator-detail-scroll">{JSON.stringify(result.connections,null,2)}</pre></details>
          <details><summary>실행 정책·버전</summary><pre className="operator-detail-scroll">{JSON.stringify({actual_scope:result.actual_scope,version:result.version},null,2)}</pre></details>
        </section>}
      </section>
    </div>
    <footer className="operator-actions"><button disabled={busy || !profile?.ready} onClick={makePreview}>새 계획 preview</button><label><input type="checkbox" checked={confirmed} disabled={!plan || Boolean(plan.job) || uncertain || busy} onChange={e=>setConfirmed(e.target.checked)}/> 표시된 계정·리소스·요청 순서와 현재 계획 digest를 확인했습니다.</label><button className="operator-primary" disabled={!canExecute({plan,confirmed,busy,uncertain,now})} onClick={run}>확인한 계획 실행</button><button onClick={()=>void recover()}>기존 상태 조회</button></footer>
  </main>;
}
