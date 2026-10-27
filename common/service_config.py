"""Operator-only service environment validation and fixed-command launchers.

No target calls, application imports, or environment mutation during validation.
This isolates known application settings, not arbitrary OS environment secrets.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from dotenv.parser import parse_stream

ROOT = Path(__file__).resolve().parents[1]
PASSWORDS = frozenset({"LAB_USER_A_PASSWORD", "LAB_USER_B_PASSWORD", "LAB_ADMIN_PASSWORD"})
KEYS = {
    "controller": frozenset("MODEL_PROVIDER OPENAI_MODEL OPENAI_API_KEY WORKER_URL TOOL_TRANSPORT MCP_WORKER_URL DATABASE_PATH RUN_MAX_CONCURRENCY WORKER_TOKEN APP_SESSION_SECRET APP_ACCESS_TOKEN APP_SESSION_TTL_SECONDS APP_SECURE_COOKIE OFFLINE_VERIFICATION_TOKEN MODEL_MAX_CALLS CONTROLLER_RUN_TIMEOUT_SECONDS UI_ALLOWED_ORIGINS UI_ALLOWED_HOSTS CONTROLLER_ALLOWED_CLIENTS".split()),
    "worker": PASSWORDS | frozenset("WORKER_TOKEN TARGET_BASE_URL TARGET_REGISTRY_PATH AGENT_MAX_STEPS HTTP_MAX_REQUESTS HTTP_TIMEOUT_SECONDS RUN_TIMEOUT_SECONDS HTTP_MAX_RESPONSE_BYTES HTTP_MAX_CONCURRENCY HTTP_REQUESTS_PER_SECOND WORKER_ALLOWED_CLIENTS MCP_ALLOWED_HOSTS MCP_ALLOWED_ORIGINS WORKER_MAX_RUNS WORKER_STATE_TTL_SECONDS".split()),
    "target": PASSWORDS | {"TARGET_DATABASE_PATH", "TARGET_MODE"},
}
ALL_KEYS = frozenset().union(*KEYS.values(), {"APP_BIND", "APP_PORT"})
SECRETS = PASSWORDS | {"WORKER_TOKEN", "APP_SESSION_SECRET", "APP_ACCESS_TOKEN", "OFFLINE_VERIFICATION_TOKEN", "OPENAI_API_KEY"}
COMMANDS = {
    "controller": ["-m", "uvicorn", "--factory", "controller.api:create_app_from_env", "--host", "192.168.56.10", "--port", "8000", "--workers", "1"],
    "worker": ["-m", "uvicorn", "--factory", "worker.app:create_app_from_env", "--host", "10.77.0.20", "--port", "9000"],
    "target": ["-m", "uvicorn", "target.app:app", "--host", "10.78.0.30", "--port", "8080"],
}


class ServiceConfigError(ValueError):
    """Messages contain only fixed diagnostics and reviewed setting names."""


def read_config(service: str, path: Path) -> dict[str, str]:
    if service not in KEYS:
        raise ServiceConfigError("unknown service")
    values = {}
    try:
        with path.open(encoding="utf-8-sig") as stream:
            for entry in parse_stream(stream):
                if entry.error:
                    raise ServiceConfigError("invalid environment file syntax")
                key = entry.key
                if key is None:
                    continue
                if key not in KEYS[service]:
                    raise ServiceConfigError("unknown or foreign-service setting")
                if key in values:
                    raise ServiceConfigError(f"duplicate setting: {key}")
                if entry.value is None or "\n" in entry.value or "\r" in entry.value or "\x00" in entry.value:
                    raise ServiceConfigError(f"invalid value: {key}")
                # No shell execution or dotenv interpolation of ambient secrets.
                if "${" in entry.value:
                    raise ServiceConfigError(f"variable interpolation is not supported: {key}")
                values[key] = entry.value
    except (OSError, UnicodeError):
        raise ServiceConfigError("cannot read service environment file") from None
    return values


def _required(values, key, minimum=1):
    value = values.get(key, "")
    if len(value.strip()) < minimum:
        raise ServiceConfigError(f"missing or too short: {key}")


def _positive(values, key, *, integer=False):
    if key not in values:
        return
    try:
        value = int(values[key]) if integer else float(values[key])
        if not math.isfinite(value) or value <= 0:
            raise ValueError()
    except (ValueError, OverflowError):
        raise ServiceConfigError(f"invalid positive limit: {key}") from None


def _worker_origin(value, *, mcp=False):
    try:
        parsed = urlsplit(value)
        ipaddress.ip_address(parsed.hostname or "")
        if (parsed.scheme != "http" or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or parsed.path != ("/mcp" if mcp else "")
                or parsed.port is None or not 1 <= parsed.port <= 65535):
            raise ValueError()
        origin = f"http://{parsed.hostname}:{parsed.port}"
        if value != origin + ("/mcp" if mcp else ""):
            raise ValueError()
        return origin
    except ValueError:
        raise ServiceConfigError("invalid worker API endpoint; use a canonical HTTP IP origin and /mcp") from None


def validate_config(service: str, values: dict[str, str]) -> dict:
    if service not in KEYS or set(values) - KEYS[service]:
        raise ServiceConfigError("unknown or foreign-service setting")
    summary = {"ok": True, "service": service, "network_requests": 0,
               "configured_settings": sorted(values),
               "configured_secrets": sorted(key for key in SECRETS if values.get(key))}
    if service in {"controller", "worker"}:
        _required(values, "WORKER_TOKEN", 16)
    if service in {"worker", "target"}:
        for key in sorted(PASSWORDS):
            _required(values, key)
    if service == "controller":
        _required(values, "APP_SESSION_SECRET", 24)
        _required(values, "APP_ACCESS_TOKEN", 16)
        auth_values = [values[key] for key in ("WORKER_TOKEN", "APP_SESSION_SECRET", "APP_ACCESS_TOKEN", "OFFLINE_VERIFICATION_TOKEN", "OPENAI_API_KEY") if values.get(key)]
        if len(set(auth_values)) != len(auth_values):
            raise ServiceConfigError("credentials for distinct controller authentication boundaries must differ")
        function = _worker_origin(values.get("WORKER_URL", "http://10.77.0.20:9000"))
        if function != _worker_origin(values.get("MCP_WORKER_URL", function + "/mcp"), mcp=True):
            raise ServiceConfigError("function and MCP must address the same worker origin")
        if values.get("MODEL_PROVIDER", "mock") not in {"mock", "openai"}:
            raise ServiceConfigError("invalid MODEL_PROVIDER")
        if values.get("TOOL_TRANSPORT", "function") not in {"function", "mcp"}:
            raise ServiceConfigError("invalid TOOL_TRANSPORT")
        if values.get("MODEL_PROVIDER", "mock") == "openai":
            _required(values, "OPENAI_API_KEY")
            _required(values, "OPENAI_MODEL")
        if values.get("APP_SECURE_COOKIE", "false") not in {"true", "false"}:
            raise ServiceConfigError("APP_SECURE_COOKIE must be true or false")
        for key in ("APP_SESSION_TTL_SECONDS", "RUN_MAX_CONCURRENCY", "MODEL_MAX_CALLS"):
            _positive(values, key, integer=True)
        _positive(values, "CONTROLLER_RUN_TIMEOUT_SECONDS")
        for key in ("UI_ALLOWED_ORIGINS", "UI_ALLOWED_HOSTS", "CONTROLLER_ALLOWED_CLIENTS"):
            if key in values and (not values[key].strip() or "*" in values[key]):
                raise ServiceConfigError(f"explicit non-wildcard allowlist required: {key}")
    elif service == "worker":
        from worker.limits import limits_from_env
        from worker.registry import load_scope_registry
        from worker.scope import ScopeViolation
        path = Path(values.get("TARGET_REGISTRY_PATH", "config/targets.json"))
        try:
            registry = load_scope_registry(path if path.is_absolute() else ROOT / path,
                                           expected_origin=values.get("TARGET_BASE_URL") or None)
            limits = limits_from_env(values)
            summary["scope_policies"] = [registry.snapshot(target, scenario, limits).record().model_dump(mode="json")
                                         for target in registry.policies for scenario in sorted(registry.profile(target).scenarios)]
        except ScopeViolation as exc:
            raise ServiceConfigError(exc.code) from None
        except (ValueError, OverflowError):
            raise ServiceConfigError("invalid global worker limits") from None
    elif values.get("TARGET_MODE", "vulnerable") not in {"vulnerable", "fixed"}:
        raise ServiceConfigError("TARGET_MODE must be vulnerable or fixed")
    return summary


def child_environment(values: dict[str, str], inherited=None) -> dict[str, str]:
    ambient = os.environ if inherited is None else inherited
    # Keep OS/runtime settings, but remove known application settings and SDK keys.
    env = {key: value for key, value in ambient.items()
           if key.upper() not in ALL_KEYS and not key.upper().startswith(("OPENAI_", "AZURE_OPENAI_"))}
    env.update(values)
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description="Check or launch one service using only its operator environment file")
    parser.add_argument("command", choices=["check", "serve"])
    parser.add_argument("service", choices=sorted(KEYS))
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    path = args.env_file or ROOT / f".env.{args.service}"
    try:
        values = read_config(args.service, path)
        summary = validate_config(args.service, values)
    except ServiceConfigError as exc:
        print(json.dumps({"ok": False, "reason_code": "SERVICE_CONFIG_INVALID", "message": str(exc)}))
        raise SystemExit(2)
    if args.command == "check":
        print(json.dumps(summary, indent=2))
        return
    try:
        result = subprocess.run([sys.executable, *COMMANDS[args.service]], cwd=ROOT,
                                env=child_environment(values), check=False)
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
