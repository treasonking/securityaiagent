import { useEffect, useRef, useState } from 'react';
import { disclosurePreview, disclosureDownload, type DisclosureReview, type Result } from './operator-api';

export default function DisclosureDraft({ run }: { run: Result }) {
  const [review, setReview] = useState<DisclosureReview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const download = useRef<AbortController | null>(null);
  useEffect(() => () => download.current?.abort(), []);

  async function preview() {
    setBusy(true); setConfirmed(false); setReview(null); setError('');
    try { setReview(await disclosurePreview(run.run_id)); }
    catch (e) { setError(e instanceof Error ? e.message : '미리보기를 열 수 없습니다.'); }
    finally { setBusy(false); }
  }

  async function issue() {
    if (!review || !confirmed || busy || download.current) return;
    const controller = new AbortController();
    download.current = controller;
    setBusy(true); setError('');
    try {
      const blob = await disclosureDownload(run.run_id, review.review_digest, controller.signal);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = run.run_id+'-internal-draft.md';
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setReview(null);
      setError(e instanceof Error ? e.message : '다운로드하지 못했습니다.');
    } finally { download.current = null; setConfirmed(false); setBusy(false); }
  }

  const eligible = run.status === 'COMPLETED' && run.conclusion?.state === 'consistent'
    && run.conclusion.verdict === 'VULNERABLE';
  return <section><h3>제보 초안 검토</h3>
    {!eligible ? <p>초안 대상 제외 · {run.status} · {run.conclusion?.label ?? '검증 불가'} · {run.conclusion?.reason_code}</p> :
      <><button disabled={busy} onClick={preview}>내부 초안 미리보기</button>
        {review && <><pre>{review.markdown}</pre>
          <label><input type="checkbox" checked={confirmed} disabled={busy}
            onChange={e=>setConfirmed(e.target.checked)}/>근거와 범위, 표현의 한계를 확인했습니다.</label>
          <button disabled={!confirmed || busy} onClick={issue}>검토한 Markdown 다운로드</button></>}
        {error && <p className="warning" role="alert">{error}</p>}</>}
  </section>;
}
