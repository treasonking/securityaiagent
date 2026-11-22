import { writeHeaders } from './api';

export type Scope = { profile_id: string; revision: number; snapshot_sha256: string; effective_limits: Record<string, number>; tls?: Record<string, string>; domain?: { hostname: string; port: number; allowed_ip_ranges: string[]; allow_non_global: boolean } };
export type Policy = { target_id: string; origin: string; scenario_id: string; contract_version: string; auth_mode: string; provider: string; accounts: { alias: string; resource_id: string }[]; scope_policy: Scope };
export type Profile = { profile_id: string; name: string; ready: boolean; policy?: Policy; message?: string; reason_code?: string; basis: string };
export type Step = { index: number; account_ref: string; operation: string; resource_id?: string; method: string; path: string };
export type Job = { plan_id: string; profile_id: string; plan_sha256: string; status: string; run_id: string | null; message?: string; reason_code?: string; created_at: number };
export type Plan = { profile_id: string; plan_id: string; plan_sha256: string; expires_at: number; transport: string; policy: Policy; sequence: Step[]; expected_http_requests: number; expected_tool_calls: number; job: Job | null; interpretation: string };
export type Conclusion = { state: "consistent" | "withheld" | "unavailable"; verdict: string; label: string; reason_code: string };
export type Result = { conclusion: Conclusion; run_id: string; status: string; verdict: string; reason_code: string; message: string | null; started_at: string; finished_at: string; transport: string; policy: Policy; usage: Record<string, number>; evidence: { evidence_id: string; account_ref: string; method: string; path: string; status_code: number; reason_code: string }[]; connections: Record<string, unknown>[]; replay: { verdict: string; verdict_matches: boolean; reason_code: string }; version: Record<string, unknown>; actual_scope: Scope | null };
export type PastRun = Pick<Result, 'conclusion' | 'run_id' | 'status' | 'verdict' | 'started_at' | 'transport'>;

export class OperatorError extends Error { constructor(public code: string, message: string) { super(message); } }
async function request<T>(path: string, body?: object): Promise<T> {
  const response = await fetch('/api/operator'+path, { credentials: 'same-origin', cache: 'no-store',
    ...(body ? { method: 'POST', headers: writeHeaders(), body: JSON.stringify(body) } : {}) });
  if (!response.ok) {
    const value = await response.json().catch(() => ({}));
    throw new OperatorError(value.detail?.code || 'REQUEST_REJECTED', value.detail?.message || '요청을 처리하지 못했습니다. 인증과 서버 설정을 확인하세요.');
  }
  return response.json();
}
export const profiles = () => request<{ profiles: Profile[]; configured: boolean; saved_results_only?: boolean; message?: string }>('/profiles');
export const preview = (profile_id: string, transport: string) => request<Plan>('/preview', { profile_id, transport });
export const getPlan = (id: string) => request<Plan>(`/plans/${encodeURIComponent(id)}`);
export const execute = (p: Plan) => request<Job>(`/plans/${encodeURIComponent(p.plan_id)}/run`, { plan_sha256: p.plan_sha256, confirmed: true });
export const jobs = () => request<{ jobs: Job[] }>('/jobs');
export const runs = () => request<{ runs: PastRun[] }>('/runs');
export const result = (id: string) => request<Result>(`/runs/${encodeURIComponent(id)}`);
export const downloadUrl = (id: string, kind: 'markdown' | 'json') => `/api/operator/runs/${encodeURIComponent(id)}/download/${kind}`;
export type DisclosureReview = { run_id: string; template_version: string; markdown: string; review_digest: string };
const disclosureUrl = (id: string) => `/runs/${encodeURIComponent(id)}/disclosure-draft`;
export const disclosurePreview = (id: string) => request<DisclosureReview>(disclosureUrl(id));
export async function disclosureDownload(id: string, review_digest: string, signal: AbortSignal) {
  const response = await fetch('/api/operator'+disclosureUrl(id), { method:'POST', headers:writeHeaders(),
    credentials:'same-origin', cache:'no-store', signal, body:JSON.stringify({ review_digest, confirmed:true }) });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail?.message || '초안을 발급하지 못했습니다. 새 미리보기를 확인하세요.');
  }
  return response.blob();
}
