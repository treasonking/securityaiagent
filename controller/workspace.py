"""Authenticated operator UI orchestration; the existing executor retains authority.

Single Controller process, single operator. Durable submission receipts are separate
from the existing database and the executor's issued/claimed plan ledger.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Literal
import uuid

from pydantic import Field
from common.api_contract import FrozenModel
from common.domain_contract import DomainObservation
from common.operator_contract import ResourceEvidence, ResourcePolicy
from common.workspace_lifecycle import admission, WorkspaceBusy
from controller.candidate_execution import CandidateError
from controller.candidates import analyse, read_local, unique, fail_constant
from controller.operator_execution import ResourceHistory, execute_plan, parse_plan, preview, validate_execution
from verifier.operator import replay_loaded

PLAN = re.compile(r'opplan_[0-9a-f]{32}')
RUN = re.compile(r'run_[0-9a-f]{32}')
PROFILE = r'^[a-z][a-z0-9-]{0,63}$'
FINAL = {'COMPLETED','FAILED','CANCELLED','TIMED_OUT','INTERRUPTED','REJECTED'}


class WorkspaceError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def diagnostic(code):
    exact = {
        'WORKSPACE_NOT_CONFIGURED': '서버에 검사 프로필이 없습니다. 운영 가이드에 따라 설정해 주세요.',
        'PROFILE_NOT_READY': '서버의 명세·등록 프로필과 Worker 정책을 확인해 주세요.',
        'PLAN_ALREADY_SUBMITTED': '이미 제출된 계획입니다. 다시 실행하지 말고 기존 상태를 조회하세요.',
        'PLAN_ALREADY_CONSUMED': '이미 사용한 계획입니다. 기존 결과를 확인하세요.',
        'PLAN_EXPIRED': '계획이 만료됐습니다. 새 preview를 확인해 주세요.',
        'PLAN_CONFIRMATION_MISMATCH': '확인한 계획 digest가 다릅니다. 새 preview를 확인해 주세요.',
        'WORKER_POLICY_CHANGED': 'Worker 정책이 바뀌었습니다. 새 preview가 필요합니다.',
        'INTERRUPTED': 'Controller 실행이 중단됐습니다. 기존 증거를 확인하고 자동 재실행하지 마세요.',
        'SAVED_INPUT_UNREADABLE': '검증 불가 · 저장된 보고서, 계약 또는 증거를 읽을 수 없습니다.',
        'NOT_FOUND': '요청한 기록을 찾을 수 없습니다.',
        'WORKSPACE_MAINTENANCE': '배포 준비 중입니다. 새 제출을 중지하고 기존 검사 이력을 확인해 주세요.',
        'WORKSPACE_BUSY': '다른 계획 작업이 진행 중입니다. 기존 상태를 먼저 확인해 주세요.',
    }
    if code in exact: return exact[code]
    if code.startswith('TLS_'): return '인증서 또는 신뢰 설정을 확인해 주세요. 안전 판정이 아니라 검사 미완료입니다.'
    if code.startswith('DNS_'): return 'DNS 결과와 승인 IP 범위를 서버에서 확인해 주세요. 검사 미완료입니다.'
    if 'POLICY' in code or 'PLAN' in code or 'REGISTRY' in code:
        return '등록 설정과 Worker 정책을 확인하고 새 preview를 발급해 주세요.'
    return '검사를 완료하지 못했습니다. 기존 실행 상태와 정제된 증거를 확인해 주세요.'


def safe_code(value):
    return value if isinstance(value,str) and re.fullmatch(r'[A-Z_]{1,64}',value) else 'WORKSPACE_OPERATION_FAILED'


def report_conclusion(replayed):
    if replayed is None:
        return dict(state='unavailable', verdict='INCONCLUSIVE', label='검증 불가',
                    reason_code='SAVED_INPUT_UNREADABLE')
    verdict = replayed['verdict']
    reason = replayed['reason_code']
    if not replayed['verdict_matches'] or reason == 'REPORT_CONTRACT_MISMATCH':
        return dict(state='withheld', verdict='INCONCLUSIVE', label='판정 보류 / 증거 불일치',
                    reason_code=reason if verdict == 'INCONCLUSIVE' else 'VERDICT_MISMATCH')
    return dict(state='consistent', verdict=verdict, label=verdict, reason_code=reason)


class Profile(FrozenModel):
    profile_id: str = Field(pattern=PROFILE)
    name: str = Field(min_length=1,max_length=80)
    source_path: str = Field(min_length=1,max_length=1024)
    registry_path: str = Field(min_length=1,max_length=1024)


class WorkspaceConfig(FrozenModel):
    schema_version: Literal['operator-workspace-v1']
    profiles: list[Profile] = Field(min_length=1,max_length=16)


def load_profiles(path):
    path = Path(path)
    config = WorkspaceConfig.model_validate(json.loads(read_local(path),object_pairs_hook=unique,parse_constant=fail_constant))
    if len({p.profile_id for p in config.profiles}) != len(config.profiles):
        raise ValueError('duplicate workspace profile')
    result = {}
    for p in config.profiles:
        paths = {k:str((path.parent/Path(getattr(p,k))).resolve()) for k in ('source_path','registry_path')}
        result[p.profile_id] = p.model_copy(update=paths)
    return result


def checked(root, *parts):
    root = Path(root).resolve()
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root): raise WorkspaceError('NOT_FOUND',404)
    for part in (path,*path.parents):
        if part == root: break
        if part.is_symlink() or part.is_junction(): raise WorkspaceError('NOT_FOUND',404)
    return path


def read_json(root,*parts):
    try:
        return json.loads(read_local(checked(root,*parts)),object_pairs_hook=unique,parse_constant=fail_constant)
    except WorkspaceError: raise
    except Exception: raise WorkspaceError('NOT_FOUND',404) from None


def write_json(path,value,exclusive=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps(value,ensure_ascii=False,indent=2)
    if exclusive:
        with path.open('x',encoding='utf-8') as f:
            f.write(content); f.flush(); os.fsync(f.fileno())
    else:
        temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        with temporary.open('x',encoding='utf-8') as f:
            f.write(content); f.flush(); os.fsync(f.fileno())
        os.replace(temporary,path)


def public_policy(policy):
    return dict(target_id=policy.target_id,origin=policy.origin,scenario_id=policy.scenario_id,
        contract_version=policy.contract_version,auth_mode=policy.adapter.auth_mode,provider='mock',
        accounts=[dict(alias=a,resource_id=policy.accounts.account(a).resource_id) for a in ('user-a','user-b')],
        scope_policy=policy.scope_policy.model_dump(mode='json'))


def public_sequence(policy):
    rows=[]
    for i,s in enumerate(policy.sequence()):
        routes=policy.adapter.routes
        method,path=(('POST',routes.login_path) if s.operation=='login' else ('GET',routes.me_path)
                     if s.operation=='identity' else ('GET',routes.detail(s.resource_id)))
        rows.append(dict(index=i+1,**s.model_dump(),method=method,path=path))
    return rows


class Workspace:
    def __init__(self, *, profiles, state_path, reports_path, policy_client, client_factory, timeout=180):
        self.profiles, self.root, self.reports = profiles,Path(state_path),Path(reports_path)
        self.pc,self.factory,self.timeout = policy_client,client_factory,timeout
        self.history=ResourceHistory(self.root/'plans')
        self.tasks=set()
        self.gate=asyncio.Semaphore(1)
        try:
            revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[1],text=True,stderr=subprocess.DEVNULL).strip()
        except Exception: revision='unavailable'
        try:
            dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=Path(__file__).resolve().parents[1],text=True,stderr=subprocess.DEVNULL).strip())
        except Exception: dirty=None
        self.version={'workspace':'operator-workspace-v1','component':'Controller',
            'commit':revision if re.fullmatch('[0-9a-f]{40}',revision) else 'unavailable',
            'working_tree_dirty':dirty,'workspace_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        self.root.mkdir(parents=True,exist_ok=True)
        for file in (self.root/'jobs').glob('opplan_*.json'):
            if not PLAN.fullmatch(file.stem): continue
            job=read_json(self.root,'jobs',file.name)
            if job['status'] not in FINAL:
                job.update(status='INTERRUPTED',reason_code='INTERRUPTED',updated_at=time.time())
                write_json(checked(self.root,'jobs',file.name),job)

    def profile(self,key):
        if key not in self.profiles: raise WorkspaceError('NOT_FOUND',404)
        return self.profiles[key]

    async def readiness(self):
        result=[]
        for p in self.profiles.values():
            row=dict(profile_id=p.profile_id,name=p.name,ready=False,transports=['function','mcp'],
                     target_contacted=False,basis='Worker 정책 조회; Target 연결 성공을 확인한 상태가 아닙니다.')
            try:
                policy=await self.pc.read()
                cat=analyse(p.source_path,p.registry_path,'lab-web')
                candidates=[r for r in cat['candidates'] if r['status']=='READY_FOR_REVIEW']
                if cat['registry_sha256']!=policy.registry_sha256 or len(candidates)!=1:
                    raise CandidateError('WORKER_REGISTRY_MISMATCH')
                row.update(ready=True,policy=public_policy(policy))
            except Exception as exc:
                code=safe_code(str(exc)) if isinstance(exc,CandidateError) else 'PROFILE_NOT_READY'
                row.update(reason_code=code,message=diagnostic(code))
            result.append(row)
        return {'profiles':result,'configured':bool(result),'message':None if result else diagnostic('WORKSPACE_NOT_CONFIGURED')}

    async def make_preview(self,key,transport):
        try:
            with admission(self.root):
                return await self._make_preview(key,transport)
        except WorkspaceBusy as exc: raise WorkspaceError(str(exc)) from None

    async def _make_preview(self,key,transport):
        p=self.profile(key)
        cat=analyse(p.source_path,p.registry_path,'lab-web')
        candidates=[r for r in cat['candidates'] if r['status']=='READY_FOR_REVIEW']
        if len(candidates)!=1: raise WorkspaceError('PROFILE_NOT_READY')
        plan=await preview(p.source_path,p.registry_path,candidates[0]['candidate_id'],transport,self.pc,self.history)
        write_json(checked(self.root,'bindings',plan.plan_id+'.json'),{'profile_id':key},exclusive=True)
        return self.plan_view(plan.plan_id)

    def plan(self,plan_id):
        if not PLAN.fullmatch(plan_id): raise WorkspaceError('NOT_FOUND',404)
        binding=read_json(self.root,'bindings',plan_id+'.json')
        p=self.profile(binding['profile_id'])
        plan=parse_plan(checked(self.root,'plans',plan_id+'.issued.json'))
        return p,plan

    def plan_view(self,plan_id):
        p,plan=self.plan(plan_id)
        job=self.job(plan_id,missing_ok=True)
        return dict(profile_id=p.profile_id,plan_id=plan.plan_id,plan_sha256=plan.plan_sha256,
            created_at=plan.created_at,expires_at=plan.expires_at,transport=plan.transport,
            policy=public_policy(plan.policy),sequence=public_sequence(plan.policy),
            expected_http_requests=11,expected_tool_calls=12,job=job,
            interpretation='준비된 두 계정·두 리소스의 관측에 한정합니다. preview는 검사 결과가 아닙니다.')

    async def submit(self,plan_id,digest):
        p,plan=self.plan(plan_id)
        if digest!=plan.plan_sha256: raise WorkspaceError('PLAN_CONFIRMATION_MISMATCH')
        receipt=checked(self.root,'jobs',plan_id+'.json')
        if receipt.exists(): raise WorkspaceError('PLAN_ALREADY_SUBMITTED')
        await validate_execution(p.source_path,p.registry_path,plan,digest,self.pc,self.history,approval_actor='human')
        job=dict(plan_id=plan_id,profile_id=p.profile_id,plan_sha256=digest,status='QUEUED',run_id=None,
                 created_at=time.time(),updated_at=time.time(),reason_code=None,version=self.version)
        try:
            with admission(self.root):
                write_json(receipt,job,exclusive=True)
        except WorkspaceBusy as exc: raise WorkspaceError(str(exc)) from None
        except FileExistsError: raise WorkspaceError('PLAN_ALREADY_SUBMITTED') from None
        task=asyncio.create_task(self._execute(p,plan,job))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return self.job(plan_id)

    async def _execute(self,p,plan,job):
        receipt=checked(self.root,'jobs',plan.plan_id+'.json')
        try:
            async with self.gate:
                job.update(status='RUNNING',updated_at=time.time())
                write_json(receipt,job)
                report=await execute_plan(p.source_path,p.registry_path,plan,plan.plan_sha256,self.pc,
                    self.history,self.factory,self.reports,approval_actor='human',timeout=self.timeout)
                job.update(status=report['status'],run_id=report['run_id'],reason_code=safe_code(report['reason_code']))
        except asyncio.CancelledError:
            job.update(status='INTERRUPTED',reason_code='INTERRUPTED')
        except Exception as exc:
            job.update(status='REJECTED',reason_code=safe_code(str(exc)) if isinstance(exc,CandidateError) else 'WORKSPACE_OPERATION_FAILED')
        finally:
            job['updated_at']=time.time()
            write_json(receipt,job)

    async def shutdown(self):
        for task in tuple(self.tasks): task.cancel()
        await asyncio.gather(*tuple(self.tasks),return_exceptions=True)

    def job(self,plan_id,missing_ok=False):
        if not PLAN.fullmatch(plan_id): raise WorkspaceError('NOT_FOUND',404)
        path=checked(self.root,'jobs',plan_id+'.json')
        if missing_ok and not path.exists(): return None
        job=read_json(self.root,'jobs',path.name)
        claimed=checked(self.root,'plans',plan_id+'.claimed.json')
        if claimed.exists():
            claim=read_json(self.root,'plans',claimed.name)
            if claim.get('plan_sha256')==job['plan_sha256'] and RUN.fullmatch(claim.get('run_id','')):
                job['run_id']=claim['run_id']
        job['message']=diagnostic(job['reason_code']) if job.get('reason_code') and job['status']!='COMPLETED' else None
        return job

    def jobs(self):
        files=sorted((self.root/'jobs').glob('opplan_*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]
        return [self.job(p.stem) for p in files if PLAN.fullmatch(p.stem)]

    def _report(self, run_id):
        if not RUN.fullmatch(run_id) or not checked(self.reports, run_id).is_dir():
            raise WorkspaceError('NOT_FOUND', 404)
        try:
            report = read_json(self.reports, run_id, 'report.json')
        except WorkspaceError:
            raise WorkspaceError('SAVED_INPUT_UNREADABLE') from None
        if not isinstance(report, dict):
            raise WorkspaceError('SAVED_INPUT_UNREADABLE')
        if report.get('schema_version') != 'operator-report-v1' or report.get('run_id') != run_id:
            raise WorkspaceError('NOT_FOUND', 404)
        return report

    def run_view(self, run_id):
        return self._view(run_id, self._report(run_id))

    def _view(self, run_id, report):
        try:
            return self._project(run_id, report)
        except (ValueError, OSError, TypeError, KeyError, AttributeError):
            raise WorkspaceError('SAVED_INPUT_UNREADABLE') from None

    def _project(self, run_id, report):
        policy = ResourcePolicy.model_validate(read_json(self.reports, run_id, 'verification_contract.json'))
        rows = read_json(self.reports, run_id, 'evidence.json')
        if not isinstance(rows, list):
            raise WorkspaceError('SAVED_INPUT_UNREADABLE')
        evidence = [ResourceEvidence.model_validate(row) for row in rows]
        connections=[]
        if checked(self.reports,run_id,'connection_observations.json').exists():
            connections=[DomainObservation.model_validate(x).model_dump(mode='json') for x in read_json(self.reports,run_id,'connection_observations.json')]
        verdict=report.get('verdict')
        status=report.get('status')
        if verdict not in {'VULNERABLE','BLOCKED_BY_ACCESS_CONTROL','INCONCLUSIVE'} or status not in FINAL:
            raise WorkspaceError('RESULT_NOT_READY')
        rerun=replay_loaded(report, policy, evidence)
        reason=safe_code(report.get('reason_code'))
        version={'workspace':'legacy-cli-record','commit':'not-recorded'}
        link=read_json(self.reports,run_id,'candidate_execution.json') if checked(self.reports,run_id,'candidate_execution.json').exists() else {}
        if PLAN.fullmatch(link.get('plan_id','')):
            job=self.job(link['plan_id'],missing_ok=True)
            if job and job.get('run_id')==run_id: version=job['version']
        return dict(conclusion=report_conclusion(rerun),run_id=run_id,status=status,verdict=verdict,reason_code=reason,
            message=diagnostic(reason) if verdict=='INCONCLUSIVE' else None,
            started_at=report.get('started_at'),finished_at=report.get('finished_at'),transport=report.get('tool_transport'),
            policy=public_policy(policy),actual_scope=report.get('scope_policy'),usage=report['limits_used'],
            sequence=public_sequence(policy),evidence=[e.model_dump(mode='json') for e in evidence],
            connections=connections,replay=rerun,
            version=version,
            model_candidates=[],verification_basis='operator_http_observation')

    def runs(self):
        result=[]
        for file in sorted(self.reports.glob('run_*/report.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:200]:
            try:
                report = self._report(file.parent.name)
            except WorkspaceError:
                continue  # Only identifiable operator reports belong in this list.
            row = {k: report.get(k) for k in ('run_id', 'status', 'verdict', 'started_at')}
            row['transport'] = report.get('tool_transport')
            try:
                row['conclusion'] = self._view(file.parent.name, report)['conclusion']
            except WorkspaceError:
                row['conclusion'] = report_conclusion(None)
            result.append(row)
        return result

    def reproduction(self,run_id):
        data=self.run_view(run_id)
        data['credential_placeholders']={'user-a':'<ACCOUNT_A_LOGIN> / <ACCOUNT_A_PASSWORD>',
            'user-b':'<ACCOUNT_B_LOGIN> / <ACCOUNT_B_PASSWORD>','session':'<COOKIE_OR_BEARER_FROM_LOGIN>'}
        current = data['conclusion']
        data['impact']=('계정 A의 교차 요청에서 준비된 비공개 리소스 B의 합성 proof가 일치했습니다.' if current['verdict']=='VULNERABLE'
            else '관측한 교차 요청은 명시적으로 거절됐습니다.' if current['verdict']=='BLOCKED_BY_ACCESS_CONTROL'
            else '접근 통제를 확정할 수 없습니다. 실패 사유와 부분 증거를 확인하세요.')
        data['limitations']='두 준비 계정·두 리소스·해당 관측 시각에 한정합니다. 실제 고객 정보 유출, 금전 피해, 심각도 또는 사이트 전체 안전성을 주장하지 않습니다.'
        data['recommendation']='서버에서 매 리소스 요청의 인증 주체와 소유권/프로젝트 권한을 검사하고 명시적으로 거절하세요.'
        if current['state'] == 'withheld':
            explanation = f"{current['label']} ({current['reason_code']})"
            data['impact'] = explanation + ' · 현재 저장 증거로 영향을 확정할 수 없습니다.'
            data['recommendation'] = explanation + ' · 보고서와 저장 증거의 대응 관계를 확인하세요.'
        data['original_verdict'] = {'verdict': data['verdict'], 'reason_code': data['reason_code']}
        return data

    def markdown(self,run_id):
        d=self.reproduction(run_id)
        sections=[f'# 접근 통제 재현 보고서 {run_id}',
            f"## 1. 검사 요약과 판정\n\n실행 상태: {d['status']} / 현재 결론: {d['conclusion']['label']}\n\n사유: {d['conclusion']['reason_code']} · {d['impact']}",
            f"## 2. 대상·관측 시각·범위\n\n{d['policy']['target_id']} · {d['policy']['origin']}\n\n{d['started_at']} → {d['finished_at']}\n\n정책: `{json.dumps(d['policy']['scope_policy'],ensure_ascii=False)}`",
            '## 3. 계정·리소스 준비\n\n서버 측 등록 프로필의 두 계정과 소유 리소스만 사용합니다. 인증정보는 운영자가 별도로 준비합니다.\n\n'+json.dumps(d['credential_placeholders'],ensure_ascii=False),
            '## 4. 요청 순서와 재현 절차\n\n등록 프로필 선택 → 새 preview → 아래 순서·정책 확인 → 현재 digest 명시적 승인 → 실행 → 저장 증거 재판정. 임의 URL이나 경로를 추가하지 않습니다.\n\n'+ '\n'.join(f"{s['index']}. {s['account_ref']} · {s['method']} `{s['path']}`" for s in d['sequence']),
            f"## 5. 기대 접근 통제와 실제 관측\n\n소유자 요청은 성공하고 다른 계정의 비공개 리소스 요청은 거절돼야 합니다.\n\n{d['impact']}\n\n실제 Worker 사용량: {d['usage']}; 최대 한도는 위 정책 참조. HTTP budget은 실제 수신 횟수와 다를 수 있습니다.",
            '## 6. 근거 evidence와 정제 관측\n\n'+ '\n'.join(f"- `{e['evidence_id']}`: {e['account_ref']} {e['method']} `{e['path']}` → {e['status_code']} / {e['reason_code']}" for e in d['evidence'])+'\n\nDNS/TLS 관측(접근 통제 판정 입력 아님):\n\n```json\n'+json.dumps(d['connections'],ensure_ascii=False,indent=2)+'\n```',
            f"## 7. 확인된 영향과 해석의 한계\n\n{d['impact']}\n\n{d['limitations']}",
            f"## 8. 수정 권고\n\n{d['recommendation']}",
            '## 9. 재판정과 실행 버전\n\n'+f"최초 판정(이력): {d['verdict']} · {d['reason_code']}\n\n"+json.dumps({'replay':d['replay'],'version':d['version']},ensure_ascii=False)+'\n\n원본 증거를 수정하지 않고 만든 파생 보고서입니다.']
        return '\n\n'.join(sections)+'\n'
