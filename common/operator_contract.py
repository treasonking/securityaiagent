"""Versioned operator-prepared resource contract; deliberately separate from canaries."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import Field, model_validator
from common.api_contract import FrozenModel, Name, Selector
from worker.candidate_policy import CandidateScope

CONTRACT = 'operator-resource-v1'
SCENARIO = 'operator-resource-http'
OpaqueId = Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')]
Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Alias = Literal['user-a', 'user-b']


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


class ResourceRoutes(FrozenModel):
    login_path: str
    me_path: str
    detail_path: str

    @model_validator(mode='after')
    def literal_paths(self):
        for path in (self.login_path, self.me_path, self.detail_path):
            if len(path) > 200 or not re.fullmatch(r'/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+(?:/\{resource_id\})?', path):
                raise ValueError('literal routes required')
        if '{' in self.login_path or '{' in self.me_path or not self.detail_path.endswith('/{resource_id}'):
            raise ValueError('only a final resource_id parameter is supported')
        if self.login_path == self.me_path:
            raise ValueError('login and identity routes must differ')
        return self

    def detail(self, resource_id):
        if not isinstance(resource_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', resource_id):
            raise ValueError('invalid opaque resource ID')
        return self.detail_path.replace('{resource_id}', resource_id)


class ResourceAccount(FrozenModel):
    principal_id: OpaqueId
    resource_id: OpaqueId
    proof_env: Literal['OPERATOR_PROOF_A', 'OPERATOR_PROOF_B']


class ResourceAccounts(FrozenModel):
    user_a: ResourceAccount
    user_b: ResourceAccount

    @model_validator(mode='after')
    def distinct(self):
        if any(getattr(self.user_a, k) == getattr(self.user_b, k) for k in ('principal_id', 'resource_id', 'proof_env')):
            raise ValueError('principals, resources and proof references must differ')
        return self

    def account(self, alias):
        if alias not in ('user-a', 'user-b'):
            raise ValueError('unknown account alias')
        return getattr(self, alias.replace('-', '_'))


class LoginRef(FrozenModel):
    username: OpaqueId
    password_env: Literal['LAB_USER_A_PASSWORD', 'LAB_USER_B_PASSWORD']


class LoginAccounts(FrozenModel):
    user_a: LoginRef
    user_b: LoginRef

    @model_validator(mode='after')
    def distinct(self):
        if self.user_a.username == self.user_b.username or self.user_a.password_env == self.user_b.password_env:
            raise ValueError('distinct login references required')
        return self


class ResourceAdapter(FrozenModel):
    contract_version: Literal['operator-resource-v1'] = CONTRACT
    adapter_id: Name
    routes: ResourceRoutes
    accounts: LoginAccounts
    login_user_field: Name = 'username'
    login_password_field: Name = 'password'
    auth_mode: Literal['cookie', 'bearer']
    cookie_name: Name | None = None
    token_field: Selector | None = None
    principal_field: Selector
    resource_id_field: Selector
    owner_field: Selector
    visibility_field: Selector
    private_value: str | bool
    public_value: str | bool
    proof_field: Selector
    denial_status: Literal[403, 404]
    denial_field: Selector
    denial_value: str = Field(min_length=1, max_length=80)

    @model_validator(mode='after')
    def semantics(self):
        if self.login_user_field == self.login_password_field:
            raise ValueError('login fields must differ')
        if self.auth_mode == 'cookie' and (not self.cookie_name or self.token_field is not None):
            raise ValueError('cookie configuration required')
        if self.auth_mode == 'bearer' and (not self.token_field or self.cookie_name is not None):
            raise ValueError('bearer configuration required')
        if type(self.private_value) is type(self.public_value) and self.private_value == self.public_value:
            raise ValueError('distinct private/public meanings required')
        if any(isinstance(v, str) and not 1 <= len(v) <= 80 for v in (self.private_value, self.public_value)):
            raise ValueError('visibility values must be bounded')
        fields = (self.resource_id_field, self.owner_field, self.visibility_field, self.proof_field)
        if len(set(fields)) != len(fields):
            raise ValueError('distinct response fields required')
        return self

    def login_payload(self, credentials):
        return {self.login_user_field: credentials[0], self.login_password_field: credentials[1]}


class ProofCommitments(FrozenModel):
    user_a: Hash
    user_b: Hash


class ResourceStep(FrozenModel):
    account_ref: Alias
    operation: Literal['login', 'identity', 'resource']
    resource_id: OpaqueId | None = None


def steps(accounts):
    a, b = accounts.user_a.resource_id, accounts.user_b.resource_id
    return tuple(ResourceStep(account_ref=who, operation=op, resource_id=rid) for who, op, rid in (
        ('user-a','login',None), ('user-b','login',None),
        ('user-a','identity',None), ('user-b','identity',None),
        ('user-a','resource',a), ('user-b','resource',b), ('user-a','resource',b),
        ('user-b','resource',b), ('user-a','resource',a),
        ('user-a','identity',None), ('user-b','identity',None)))


class ResourcePolicy(FrozenModel):
    contract_version: Literal['operator-resource-v1'] = CONTRACT
    target_id: Literal['lab-web'] = 'lab-web'
    scenario_id: Literal['operator-resource-http'] = SCENARIO
    registry_sha256: Hash
    origin: str = Field(max_length=200)
    adapter: ResourceAdapter
    accounts: ResourceAccounts
    proof_commitments: ProofCommitments
    scope_policy: CandidateScope

    @model_validator(mode='after')
    def tls_identity(self):
        if self.origin.startswith('https://') != (self.scope_policy.tls is not None):
            raise ValueError('HTTPS requires versioned TLS identity; HTTP keeps its original contract')
        return self

    def sequence(self):
        return steps(self.accounts)


class ResourceEvidence(FrozenModel):
    schema_version: Literal['operator-evidence-v1'] = 'operator-evidence-v1'
    contract_version: Literal['operator-resource-v1'] = CONTRACT
    run_id: str = Field(min_length=1, max_length=128)
    evidence_id: Hash
    request_id: str = Field(min_length=1, max_length=128)
    snapshot_sha256: Hash
    step_index: int = Field(ge=0, le=10)
    account_ref: Alias
    operation: Literal['login', 'identity', 'resource']
    method: Literal['GET', 'POST']
    path: str = Field(max_length=330)
    status_code: int = Field(ge=100, le=599)
    session_binding: Hash
    response_kind: Literal['login', 'identity', 'private_resource', 'denied', 'unknown']
    principal_ref: Alias | None = None
    resource_ref: Alias | None = None
    owner_ref: Alias | None = None
    proof_ref: Alias | None = None
    proof_digest: Hash | None = None
    proof_present: bool = False
    reason_code: str = Field(pattern=r'^[A-Z_]{1,64}$')


class ResourceResult(FrozenModel):
    ok: bool
    run_id: str
    scope_policy: CandidateScope | None = None
    request_count: int = Field(default=0, ge=0)
    tool_count: int = Field(default=0, ge=0)
    evidence: ResourceEvidence | None = None
    error_code: str | None = None
