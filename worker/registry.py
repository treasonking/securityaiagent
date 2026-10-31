from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, ValidationError

from common.api_contract import ApiAdapter
from worker.limits import WorkerLimits
from worker.policy import PolicyViolation, TargetPolicy
from worker.scope import ScopeProfile, ScopeSnapshot, ScopeViolation, make_snapshot


DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "config" / "targets.json"


class RegisteredTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    origin: str
    profile: ScopeProfile
    adapter: ApiAdapter = ApiAdapter()


class RegistryFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["2.0"]
    targets: dict[Literal["lab-web"], RegisteredTarget]


@dataclass(frozen=True)
class ScopeRegistry:
    policies: Mapping[str, TargetPolicy]
    # Canonical JSON prevents later mutation of nested profile mappings.
    profiles_json: Mapping[str, str]
    adapters_json: Mapping[str, str]

    def profile(self, target_id: str) -> ScopeProfile:
        if target_id not in self.profiles_json:
            raise ScopeViolation("SCOPE_TARGET_DENIED", "target is not registered")
        return ScopeProfile.model_validate(json.loads(self.profiles_json[target_id]))

    def snapshot(self, target_id: str, scenario: str, limits: WorkerLimits) -> ScopeSnapshot:
        profile = self.profile(target_id)
        return make_snapshot(self.policies[target_id], profile, scenario, limits, self.adapter(target_id))

    def adapter(self, target_id: str) -> ApiAdapter:
        return ApiAdapter.model_validate(json.loads(self.adapters_json[target_id]))

    def config_digest(self, target_id: str) -> str:
        value = {'origin': self.policies[target_id].base_url, 'profile': self.profile(target_id).normalized(),
                 'adapter': self.adapter(target_id).model_dump(mode='json')}
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

    def credentials(self, environ) -> dict[str, tuple[str, str]]:
        adapter = self.adapter("lab-web")
        result = {}
        for account in ("user-a", "user-b", "admin"):
            ref = getattr(adapter.accounts, account.replace("-", "_"))
            value = environ.get(ref.password_env)
            if not value:
                raise ScopeViolation("SCOPE_ACCOUNT_DENIED", "adapter credential environment reference is unset")
            result[account] = (ref.username, value)
        return result

    def with_test_origins(self, policies: Mapping[str, TargetPolicy]) -> ScopeRegistry:
        """Code-only synthetic test injection, never an HTTP/env URL override."""
        if set(policies) != set(self.policies) or any(key != policy.target_id for key, policy in policies.items()):
            raise ScopeViolation("SCOPE_TARGET_DENIED", "test origins must preserve registered target IDs")
        return ScopeRegistry(MappingProxyType(dict(policies)), self.profiles_json, self.adapters_json)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError("nonfinite JSON number")


def load_scope_registry(path: str | Path = DEFAULT_REGISTRY, *, expected_origin: str | None = None) -> ScopeRegistry:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object, parse_constant=_nonfinite)
        registry = RegistryFile.model_validate(payload)
        if not registry.targets:
            raise ValueError("empty registry")
        policies, profiles, adapters = {}, {}, {}
        for target_id, target in registry.targets.items():
            parsed = urlsplit(target.origin)
            policy = TargetPolicy(target_id, parsed.scheme, parsed.hostname or "", parsed.port or 80)
            if target.origin != policy.base_url:
                raise ScopeViolation("SCOPE_ORIGIN_MISMATCH", "registered origin must be canonical and contain no path or credentials")
            if expected_origin is not None and expected_origin != policy.base_url:
                raise ScopeViolation("SCOPE_ORIGIN_MISMATCH", "TARGET_BASE_URL differs from the registered origin")
            if not target.profile.enabled:
                raise ScopeViolation("SCOPE_DISABLED", "scope profile is disabled")
            if target.adapter.routes != target.profile.http_routes:
                raise ScopeViolation("SCOPE_ADAPTER_MISMATCH", "adapter routes are not approved by scope")
            if "access-control" in target.profile.scenarios and target.adapter != ApiAdapter():
                raise ScopeViolation("SCOPE_SCENARIO_DENIED", "legacy log scenario requires the default adapter")
            adapters[target_id] = target.adapter.model_dump_json()
            policies[target_id] = policy
            profiles[target_id] = json.dumps(target.profile.normalized(), sort_keys=True, allow_nan=False)
        return ScopeRegistry(MappingProxyType(policies), MappingProxyType(profiles), MappingProxyType(adapters))
    except ScopeViolation:
        raise
    except (OSError, ValueError, TypeError, ValidationError, PolicyViolation):
        raise ScopeViolation("SCOPE_INVALID", "scope registry is missing or invalid; check the operator file") from None


def load_target_registry(path: str | Path) -> dict[str, TargetPolicy]:
    return dict(load_scope_registry(path).policies)
