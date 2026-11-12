"""Operator control contract, deliberately not a model tool."""
from typing import Annotated, Literal

from pydantic import Field
from common.api_contract import FrozenModel, HttpRoutes, Name
from worker.scope import ProfileLimits

CONTRACT = 'candidate-preview-v1'
Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class CandidateScope(FrozenModel):
    profile_id: Name
    revision: int = Field(gt=0)
    snapshot_sha256: Hash
    effective_limits: ProfileLimits


class CandidatePolicy(FrozenModel):
    contract_version: Literal['candidate-preview-v1'] = CONTRACT
    target_id: Literal['lab-web'] = 'lab-web'
    scenario_id: Literal['access-control-http'] = 'access-control-http'
    registry_sha256: Hash
    origin: str = Field(max_length=200)
    adapter_id: Name
    auth_mode: Literal['cookie', 'bearer']
    routes: HttpRoutes
    scope_policy: CandidateScope


def policy_for(service):
    scope = service.registry.snapshot('lab-web', 'access-control-http', service.limits)
    for account in ('user-a', 'user-b'):
        for operation in ('login', 'list_own_documents', 'fetch_document'):
            scope.authorize(account, operation)
    return CandidatePolicy(registry_sha256=service.registry.config_digest('lab-web'),
        origin=scope.target.base_url, adapter_id=scope.adapter.adapter_id,
        auth_mode=scope.adapter.auth_mode, routes=scope.http_routes,
        scope_policy=CandidateScope.model_validate(scope.record().model_dump(mode='json')))
