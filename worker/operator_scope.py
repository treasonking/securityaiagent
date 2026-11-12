"""Operator authority for a separate schema 2.0 resource profile."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field, replace
import json
import re
from types import MappingProxyType
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from common.api_contract import FrozenModel
from common.operator_contract import (CONTRACT, SCENARIO, ResourceAccounts, ResourceAdapter,
    ResourceRoutes, ResourcePolicy, ProofCommitments, canonical, digest, steps)
from worker.scope import ProfileLimits, ScopeViolation
from worker.limits import WorkerLimits
from worker.policy import TargetPolicy, PolicyViolation
from worker.candidate_policy import CandidateScope


class ResourceProfile(FrozenModel):
    profile_id: str = Field(pattern=r'^[a-z][a-z0-9-]{0,63}$')
    revision: int = Field(gt=0)
    enabled: bool
    scenario_id: Literal['operator-resource-http'] = SCENARIO
    accounts: ResourceAccounts
    http_routes: ResourceRoutes
    limits: ProfileLimits

    @property
    def scenarios(self):
        return {SCENARIO: ('user-a', 'user-b')}

    def normalized(self):
        return self.model_dump(mode='json')


class OperatorTarget(FrozenModel):
    origin: str
    profile: ResourceProfile
    adapter: ResourceAdapter

    @model_validator(mode='after')
    def approved(self):
        if not self.profile.enabled or self.adapter.routes != self.profile.http_routes:
            raise ValueError('operator scope disabled or routes not approved')
        return self


class OperatorFile(FrozenModel):
    schema_version: Literal['2.0']
    targets: dict[Literal['lab-web'], OperatorTarget]


@dataclass(frozen=True)
class OperatorSnapshot:
    target: TargetPolicy
    policy: ResourcePolicy
    limits: WorkerLimits

    @property
    def scenario_id(self): return SCENARIO
    @property
    def adapter(self): return self.policy.adapter
    @property
    def snapshot_sha256(self): return self.policy.scope_policy.snapshot_sha256
    @property
    def http_routes(self): return self.adapter.routes
    @property
    def accounts(self): return ('user-a', 'user-b')
    @property
    def operations(self): return ('login', 'identity', 'resource')
    def record(self): return self.policy.scope_policy

    def path(self, step):
        return (('POST', self.http_routes.login_path) if step.operation == 'login' else
                ('GET', self.http_routes.me_path) if step.operation == 'identity' else
                ('GET', self.http_routes.detail(step.resource_id)))

    def authorize_request(self, target, account, operation, method, path):
        if target != self.target:
            raise ScopeViolation('SCOPE_ORIGIN_MISMATCH', 'registered origin required')
        if account not in self.accounts:
            raise ScopeViolation('SCOPE_ACCOUNT_DENIED', 'registered account required')
        if path != target.normalize_relative_path(path):
            raise ScopeViolation('SCOPE_PATH_DENIED', 'canonical path required')
        allowed = [(s.account_ref, s.operation, *self.path(s)) for s in self.policy.sequence()]
        if (account, operation, method, path) not in allowed:
            raise ScopeViolation('SCOPE_RESOURCE_DENIED', 'request not in the approved read flow')


@dataclass(frozen=True)
class OperatorRegistry:
    policies: object
    target_json: str
    proof_values: object = field(default=None, repr=False)

    def registered(self): return OperatorTarget.model_validate(json.loads(self.target_json))
    def profile(self, target_id):
        if target_id != 'lab-web':
            raise ScopeViolation('SCOPE_TARGET_DENIED', 'target is not registered')
        return self.registered().profile
    def adapter(self, target_id):
        self.profile(target_id)
        return self.registered().adapter
    def config_digest(self, target_id):
        self.profile(target_id)
        value = self.registered().model_dump(mode='json')
        value['origin'] = self.policies[target_id].base_url
        return digest(canonical(value))
    def credentials(self, environ):
        out = {}
        for alias in ('user-a', 'user-b'):
            ref = getattr(self.adapter('lab-web').accounts, alias.replace('-', '_'))
            password = environ.get(ref.password_env)
            if not isinstance(password, str) or not password:
                raise ScopeViolation('SCOPE_ACCOUNT_DENIED', 'credential reference is unset')
            out[alias] = (ref.username, password)
        return out
    def bind_proofs(self, environ):
        values = {a: environ.get(self.profile('lab-web').accounts.account(a).proof_env) for a in ('user-a','user-b')}
        if (any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', v) for v in values.values())
                or values['user-a'] == values['user-b']):
            raise ScopeViolation('PROOF_CONFIGURATION_INVALID', 'distinct high-entropy proof references are required')
        return replace(self, proof_values=MappingProxyType(values))
    def with_test_origins(self, policies):
        if set(policies) != {'lab-web'} or policies['lab-web'].target_id != 'lab-web':
            raise ScopeViolation('SCOPE_TARGET_DENIED', 'test origin must preserve target ID')
        return replace(self, policies=MappingProxyType(dict(policies)))
    def snapshot(self, target_id, scenario, limits):
        profile = self.profile(target_id)
        if scenario != SCENARIO:
            raise ScopeViolation('SCOPE_SCENARIO_DENIED', 'resource scenario required')
        if self.proof_values is None:
            raise ScopeViolation('PROOF_CONFIGURATION_INVALID', 'worker proof binding required')
        values = {k: (getattr(profile.limits,k) if k=='requests_per_second' and v==0 else min(v,getattr(profile.limits,k))) for k,v in asdict(limits).items()}
        values['max_requests'] = min(11, values['max_requests'])
        values['max_tool_calls'] = min(12, values['max_tool_calls'])
        effective = WorkerLimits(**values)
        commitments = ProofCommitments(**{a.replace('-','_'): digest(b'operator-proof-v1\0'+v.encode()) for a,v in self.proof_values.items()})
        binding = dict(contract_version=CONTRACT, registry_sha256=self.config_digest(target_id),
            proof_commitments=commitments.model_dump(mode='json'), effective_limits=asdict(effective),
            sequence=[s.model_dump(mode='json') for s in steps(profile.accounts)])
        policy = ResourcePolicy(registry_sha256=self.config_digest(target_id), origin=self.policies[target_id].base_url,
            adapter=self.adapter(target_id), accounts=profile.accounts, proof_commitments=commitments,
            scope_policy=CandidateScope(profile_id=profile.profile_id,revision=profile.revision,
                snapshot_sha256=digest(canonical(binding)),effective_limits=profile.limits.model_validate(asdict(effective))))
        return OperatorSnapshot(self.policies[target_id],policy,effective)


def parse_operator_registry(payload, expected_origin=None):
    try:
        doc = OperatorFile.model_validate(payload)
        if set(doc.targets) != {'lab-web'}: raise ValueError()
        entry = doc.targets['lab-web']
        url = urlsplit(entry.origin)
        target = TargetPolicy('lab-web',url.scheme,url.hostname or '',url.port or 80)
        if entry.origin != target.base_url or expected_origin is not None and expected_origin != target.base_url:
            raise ValueError()
        return OperatorRegistry(MappingProxyType({'lab-web':target}),entry.model_dump_json())
    except (ValueError, TypeError, PolicyViolation):
        raise ScopeViolation('SCOPE_INVALID','invalid operator resource registry') from None
