from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import httpx
import pytest

from common.schemas import RunReport
from controller.engine import EngineRequest, RunEngine
from controller.providers import MockModelProvider
from controller.reporting import ReportWriter
from controller.tool_clients import DirectToolClient, FunctionWorkerClient, MCPWorkerClient
from tests.helpers import make_service
from scripts.run_http_verification import local_server
from tests.test_worker_limits import LoginTransport, BlockingTransport
from worker.app import build_worker_app, create_app_from_env
from worker.limits import WorkerLimits
from worker.policy import TargetPolicy
from worker.registry import DEFAULT_REGISTRY, load_scope_registry
from worker.scope import ScopeViolation
from worker.service import ToolService


def policy_payload():
    return json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))


def write_policy(tmp_path, payload=None):
    path = tmp_path / "targets.json"
    path.write_text(json.dumps(payload if payload is not None else policy_payload()), encoding="utf-8")
    return path


def service_for(tmp_path, *, profile_changes=None, limit_changes=None, global_limits=None, transport=None):
    payload = policy_payload()
    profile = payload["targets"]["lab-web"]["profile"]
    profile.update(profile_changes or {})
    # Positive, bounded pacing for unit tests only; production config remains 2/s.
    profile["limits"].update(requests_per_second=10000.0)
    profile["limits"].update(limit_changes or {})
    path = write_policy(tmp_path, payload)
    registry = load_scope_registry(path)
    transport = transport or LoginTransport()
    service = ToolService(registry=registry, accounts={"user-a": ("user_a", "fake-password-a"),
                         "user-b": ("user_b", "fake-password-b"), "admin": ("admin", "fake-password-admin")},
                         transport=transport, limits=global_limits or WorkerLimits(requests_per_second=0))
    return service, transport, path


@pytest.mark.parametrize("field", ["max_requests", "max_tool_calls", "max_response_bytes", "max_concurrency", "max_runs",
                                  "timeout_seconds", "run_timeout_seconds", "requests_per_second", "state_ttl_seconds"])
@pytest.mark.parametrize("value", [True, False, 0, -1, "2", float("nan"), float("inf")])
def test_invalid_profile_limits_fail_closed(tmp_path, field, value):
    payload = policy_payload()
    payload["targets"]["lab-web"]["profile"]["limits"][field] = value
    with pytest.raises(ScopeViolation) as error:
        load_scope_registry(write_policy(tmp_path, payload))
    assert error.value.code == "SCOPE_INVALID"


@pytest.mark.parametrize("case", ["unknown-key", "unknown-profile-key", "unknown-scenario", "unknown-account", "unknown-operation",
                                  "duplicate-account", "duplicate-operation", "empty-scenarios", "missing-origin", "missing-profile",
                                  "disabled", "missing-target", "unknown-target", "boolean-revision", "zero-revision", "unknown-version",
                                  "http-admin", "numeric-enabled", "fractional-count", "missing-limit", "string-limits", "raw-credential"])
def test_invalid_registry_references_and_profiles(tmp_path, case):
    payload = policy_payload()
    target = payload["targets"]["lab-web"]
    profile = target["profile"]
    if case == "unknown-key": payload["untrusted-secret"] = "never-echo-this"
    elif case == "unknown-profile-key": profile["shell"] = "never-echo-this"
    elif case == "unknown-scenario": profile["scenarios"]["arbitrary"] = ["user-a"]
    elif case == "unknown-account": profile["scenarios"]["access-control"] = ["root"]
    elif case == "unknown-operation": profile["operations"] = ["delete_document"]
    elif case == "duplicate-account": profile["scenarios"]["access-control"] = ["user-a", "user-a"]
    elif case == "duplicate-operation": profile["operations"] = ["login", "login"]
    elif case == "empty-scenarios": profile["scenarios"] = {}
    elif case == "missing-origin": target.pop("origin")
    elif case == "missing-profile": target.pop("profile")
    elif case == "disabled": profile["enabled"] = False
    elif case == "missing-target": payload["targets"] = {}
    elif case == "unknown-target": payload["targets"]["external"] = target
    elif case == "boolean-revision": profile["revision"] = True
    elif case == "zero-revision": profile["revision"] = 0
    elif case == "unknown-version": payload["schema_version"] = "1.0"
    elif case == "http-admin": profile["scenarios"]["access-control-http"] = ["admin"]
    elif case == "numeric-enabled": profile["enabled"] = 1
    elif case == "fractional-count": profile["limits"]["max_requests"] = 1.5
    elif case == "missing-limit": profile["limits"].pop("max_requests")
    elif case == "string-limits": profile["limits"] = "never-echo-this"
    elif case == "raw-credential": profile["password"] = "never-echo-this"
    with pytest.raises(ScopeViolation) as error:
        load_scope_registry(write_policy(tmp_path, payload))
    assert error.value.code == ("SCOPE_DISABLED" if case == "disabled" else "SCOPE_INVALID")
    assert "never-echo-this" not in str(error.value)


@pytest.mark.parametrize("origin", ["http://example.com:8080", "http://*.example.com:8080", "https://10.78.0.30:8080",
                                    "http://u:secret@10.78.0.30:8080", "http://10.78.0.30:8080/", "http://10.78.0.30:8080?x=y",
                                    "http://10.78.0.30:8080#fragment", "http://10.78.0.30:0", "http://10.78.0.30:65536"])
def test_origin_is_canonical_http_ip_literal(tmp_path, origin):
    payload = policy_payload()
    payload["targets"]["lab-web"]["origin"] = origin
    with pytest.raises(ScopeViolation): load_scope_registry(write_policy(tmp_path, payload))


def test_duplicate_json_keys_and_missing_file_do_not_fallback(tmp_path):
    path = write_policy(tmp_path)
    path.write_text(path.read_text().replace('"revision": 1', '"revision": 1, "revision": 2'))
    with pytest.raises(ScopeViolation): load_scope_registry(path)
    with pytest.raises(ScopeViolation): load_scope_registry(tmp_path / "missing.json")


def test_worker_startup_rejects_environment_origin_override(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_REGISTRY_PATH", str(write_policy(tmp_path)))
    monkeypatch.setenv("TARGET_BASE_URL", "http://127.0.0.1:12345")
    monkeypatch.setenv("WORKER_TOKEN", "fake-worker-token")
    with pytest.raises(ScopeViolation) as error: create_app_from_env()
    assert error.value.code == "SCOPE_ORIGIN_MISMATCH"


@pytest.mark.parametrize("field,value", [("max_requests", True), ("max_requests", 1.5), ("timeout_seconds", float("nan")),
                                       ("requests_per_second", float("inf")), ("requests_per_second", False), ("max_runs", 0)])
def test_global_limits_are_also_strict(field, value):
    with pytest.raises(ValueError): WorkerLimits(**{field: value})


@pytest.mark.parametrize("case,code", [("account", "SCOPE_ACCOUNT_DENIED"), ("scenario", "SCOPE_SCENARIO_DENIED"),
                                     ("operation", "SCOPE_OPERATION_DENIED"), ("target", "SCOPE_TARGET_DENIED")])
def test_start_denials_send_zero_requests(tmp_path, case, code):
    changes = {}
    if case == "account": changes["scenarios"] = {"access-control-http": ["user-a"]}
    if case == "scenario": changes["scenarios"] = {"access-control": ["user-a"]}
    if case == "operation": changes["operations"] = ["fetch_document"]
    service, transport, _ = service_for(tmp_path, profile_changes=changes)
    result = asyncio.run(service.start_session("denied", "outside" if case == "target" else "lab-web", "user-b", "access-control-http"))
    assert result.error_code == code
    assert transport.request_count == 0 and not service._runs


@pytest.mark.parametrize("global_cap,profile_cap,scenario,expected", [(2, 5, "access-control", 2), (8, 3, "access-control", 3),
                                                                    (50, 40, "access-control-http", 9)])
def test_most_restrictive_budget_stops_n_plus_one(tmp_path, global_cap, profile_cap, scenario, expected):
    service, transport, _ = service_for(tmp_path, limit_changes={"max_requests": profile_cap, "max_tool_calls": 50},
                                       global_limits=WorkerLimits(max_requests=global_cap, max_tool_calls=50, requests_per_second=0))
    async def go():
        for _ in range(expected):
            result = await service.start_session("cap", "lab-web", "user-a", scenario)
            assert result.ok
        result = await service.start_session("cap", "lab-web", "user-a", scenario)
        assert result.error_code == "SCOPE_LIMIT_EXCEEDED"
        assert result.scope_policy.effective_limits["max_requests"] == expected
        assert result.data["request_count"] == expected
    asyncio.run(go())
    assert transport.request_count == expected


def test_snapshot_is_immutable_and_files_apply_only_on_restart(tmp_path):
    service, transport, path = service_for(tmp_path, limit_changes={"max_requests": 1})
    async def go():
        first = await service.start_session("old", "lab-web", "user-a")
        snapshot = service._runs["old"].scope
        with pytest.raises(FrozenInstanceError): snapshot.revision = 100
        payload = json.loads(path.read_text())
        payload["targets"]["lab-web"]["profile"]["revision"] = 2
        payload["targets"]["lab-web"]["profile"]["limits"]["max_requests"] = 5
        path.write_text(json.dumps(payload))
        assert (await service.start_session("old", "lab-web", "user-a")).error_code == "SCOPE_LIMIT_EXCEEDED"
        new_same_process = await service.start_session("same-worker", "lab-web", "user-a")
        assert new_same_process.scope_policy == first.scope_policy
        restarted = ToolService(registry=load_scope_registry(path), accounts=service.accounts, transport=transport,
                                limits=service.limits)
        new = await restarted.start_session("new-worker", "lab-web", "user-a")
        assert new.scope_policy.revision == 2
        assert new.scope_policy.snapshot_sha256 != first.scope_policy.snapshot_sha256
        assert (await restarted.start_session("new-worker", "lab-web", "user-a")).ok
    asyncio.run(go())


@pytest.mark.parametrize("path", ["//203.0.113.1/a", "http://203.0.113.1/a", "/documents/../login", "/documents/%2e%2e/login",
                                  "/documents/doc-a-001?x=y", "/documents/doc-a-001#x", "/%2f%2fevil.example/a",
                                  "/documents/doc-a-001%3Fx=y", "/documents/doc-a-001%2523x"])
def test_path_bypass_rejected_at_final_send_gate(tmp_path, path):
    service, transport, _ = service_for(tmp_path)
    async def go():
        first = await service.start_session("gate", "lab-web", "user-a")
        state = service._runs["gate"]
        ref = first.data["session_ref"]
        with pytest.raises(ScopeViolation):
            await service._request(state, state.scope.target, operation="fetch_document", method="GET", path=path,
                                   account_ref="user-a", session_ref=ref, cookies=state.sessions[ref].cookies)
        assert state.request_count == 1
    asyncio.run(go())
    assert transport.request_count == 1


@pytest.mark.parametrize("case", ["origin", "method", "operation", "session", "account", "cookies", "payload"])
def test_final_gate_binds_operation_origin_account_and_session(tmp_path, case):
    service, transport, _ = service_for(tmp_path)
    async def go():
        first = await service.start_session("gate", "lab-web", "user-a")
        state = service._runs["gate"]
        ref = first.data["session_ref"]
        kwargs = dict(operation="fetch_document", method="GET", path="/documents/doc-a-001", account_ref="user-a",
                      session_ref=ref, cookies=state.sessions[ref].cookies)
        policy = state.scope.target
        if case == "origin": policy = TargetPolicy("lab-web", "http", "203.0.113.1", 8080)
        if case == "method": kwargs["method"] = "POST"
        if case == "operation": kwargs["operation"] = "logout"
        if case == "session": kwargs["session_ref"] = "other-session"
        if case == "account": kwargs["account_ref"] = "user-b"
        if case == "cookies": kwargs["cookies"] = httpx.Cookies({"lab_session": "other"})
        if case == "payload": kwargs["json"] = {"write": "forbidden"}
        with pytest.raises(ScopeViolation): await service._request(state, policy, **kwargs)
        assert state.request_count == 1
    asyncio.run(go())
    assert transport.request_count == 1


def test_policy_gate_is_rechecked_after_wait_before_send(tmp_path):
    service, transport, _ = service_for(tmp_path)
    async def go():
        result = await service.start_session("gate", "lab-web", "user-a")
        ref = result.data["session_ref"]
        await service._http_semaphore.acquire()
        waiting = asyncio.create_task(service.list_own_documents("gate", "lab-web", ref))
        await asyncio.sleep(0.01)
        service._runs["gate"].sessions.pop(ref)
        service._http_semaphore.release()
        result = await waiting
        assert result.error_code == "SCOPE_SESSION_DENIED"
        assert result.data["request_count"] == 1
    asyncio.run(go())
    assert transport.request_count == 1


def test_profile_rate_and_concurrency_remain_enforced_with_global_zero(tmp_path):
    service, transport, _ = service_for(tmp_path, limit_changes={"requests_per_second": 0.5})
    async def rate():
        first = await service.start_session("rate", "lab-web", "user-a")
        assert first.scope_policy.effective_limits["requests_per_second"] == 0.5
        waiting = asyncio.create_task(service.list_own_documents("rate", "lab-web", first.data["session_ref"]))
        await asyncio.sleep(0.03)
        await service.cancel_run("rate")
        assert not (await waiting).ok
    asyncio.run(rate())
    assert transport.request_count == 1
    blocker = BlockingTransport()
    service, _, _ = service_for(tmp_path, limit_changes={"max_concurrency": 1},
                                global_limits=WorkerLimits(max_concurrency=3, requests_per_second=0), transport=blocker)
    async def concurrency():
        first = asyncio.create_task(service.start_session("one", "lab-web", "user-a"))
        await blocker.started.wait()
        second = asyncio.create_task(service.start_session("two", "lab-web", "user-a"))
        await asyncio.sleep(0.03)
        assert blocker.request_count == 1
        await service.cancel_run("two")
        assert not (await second).ok
        blocker.release.set()
        assert (await first).ok
    asyncio.run(concurrency())


def test_offline_checker_outputs_normalized_scope_and_redacted_failures(tmp_path):
    path = write_policy(tmp_path)
    env = {**os.environ, "PYTHONUTF8": "1", "TARGET_BASE_URL": "http://10.78.0.30:8080"}
    cmd = [sys.executable, "-m", "worker.cli", "check-policy", "--registry", str(path)]
    result = subprocess.run(cmd, text=True, capture_output=True, env=env)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert len(data["policies"]) == 2
    assert data["policies"][1]["effective_limits"]["max_requests"] == 9
    path.write_text('{"password":"secret-must-not-appear"}')
    bad = subprocess.run(cmd, text=True, capture_output=True, env=env)
    assert bad.returncode == 2 and json.loads(bad.stdout)["reason_code"] == "SCOPE_INVALID"
    assert "secret-must-not-appear" not in bad.stdout + bad.stderr


def test_fingerprint_is_normalized_and_changes_with_policy(tmp_path):
    path = write_policy(tmp_path)
    first = load_scope_registry(path).snapshot("lab-web", "access-control-http", WorkerLimits())
    payload = json.loads(path.read_text())
    profile = payload["targets"]["lab-web"]["profile"]
    profile["operations"].reverse()
    profile["scenarios"]["access-control-http"].reverse()
    path.write_text(json.dumps(payload, indent=4))
    assert load_scope_registry(path).snapshot("lab-web", "access-control-http", WorkerLimits()) == first
    profile["revision"] += 1
    path.write_text(json.dumps(payload))
    assert load_scope_registry(path).snapshot("lab-web", "access-control-http", WorkerLimits()).snapshot_sha256 != first.snapshot_sha256


@pytest.mark.parametrize("transport_name", ["function", "mcp"])
def test_both_transports_enforce_worker_scope_with_zero_target_requests(tmp_path, transport_name):
    service, target, _ = service_for(tmp_path, profile_changes={"scenarios": {"access-control-http": ["user-a"]}})
    with local_server(build_worker_app(service, worker_token="fake-test-worker-token", allowed_clients={"127.0.0.1"})) as port:
        base = f"http://127.0.0.1:{port}"
        client = FunctionWorkerClient(base_url=base, token="fake-test-worker-token") if transport_name == "function" else MCPWorkerClient(server_url=base + "/mcp", token="fake-test-worker-token")
        async def go():
            async with client.session():
                result = await client.start_session("denied", "lab-web", "user-b", "access-control-http")
                assert result.error_code == "SCOPE_ACCOUNT_DENIED"
        asyncio.run(go())
    assert target.request_count == 0


def test_legacy_report_keeps_absent_policy_metadata():
    path = next(Path("reports/http_verification").glob("*/report.json"))
    report = json.loads(path.read_text(encoding="utf-8"))
    assert "scope_policy" not in report
    parsed = RunReport.model_validate(report)
    assert parsed.scope_policy is None


@pytest.mark.parametrize("limit", ["max_response_bytes", "timeout_seconds", "run_timeout_seconds"])
def test_profile_response_and_time_limits_actually_stop_io(tmp_path, limit):
    async def respond(request):
        if limit != "max_response_bytes":
            await asyncio.sleep(0.1)
        return httpx.Response(200, content=b"x" * 100, headers={"set-cookie": "lab_session=fake; Path=/"})
    value = 10 if limit == "max_response_bytes" else 0.01
    service, _, _ = service_for(tmp_path, limit_changes={limit: value}, transport=httpx.MockTransport(respond))
    async def go():
        result = await service.start_session("limited", "lab-web", "user-a")
        assert result.error_code == "SCOPE_LIMIT_EXCEEDED"
        assert result.scope_policy.effective_limits[limit] == value
        assert result.data["request_count"] == 1
        assert not (await service.finish_run("limited")).ok
    asyncio.run(go())


def test_profile_run_capacity_and_failed_state_expiry(tmp_path):
    service, transport, _ = service_for(tmp_path, limit_changes={"max_runs": 1, "state_ttl_seconds": 0.02})
    async def go():
        assert (await service.start_session("one", "lab-web", "user-a")).ok
        denied = await service.start_session("two", "lab-web", "user-a")
        assert denied.error_code == "SCOPE_LIMIT_EXCEEDED" and transport.request_count == 1
        failed = await service.start_session("one", "lab-web", "admin", "access-control-http")
        assert failed.error_code == "SCOPE_SESSION_DENIED"
        assert not service._runs["one"].sessions
        await asyncio.sleep(0.03)
        assert (await service.start_session("two", "lab-web", "user-a")).ok
    asyncio.run(go())


@pytest.mark.parametrize("scenario", ["access-control", "access-control-http"])
@pytest.mark.parametrize("failure", ["missing", "changed", "finish-denied"])
def test_controller_never_confirms_incomplete_or_mismatched_scope(tmp_path, scenario, failure):
    service, _ = make_service(tmp_path, "vulnerable")
    class ChangedClient(DirectToolClient):
        async def finish_run(self, run_id):
            result = await super().finish_run(run_id)
            if failure == "missing":
                result.scope_policy = None
            elif failure == "changed":
                result.scope_policy = result.scope_policy.model_copy(update={"revision": 999})
            else:
                result.ok = False
                result.error_code = "SCOPE_LIMIT_EXCEEDED"
            return result
    events = []
    async def emit(event, payload):
        events.append((event, payload))
    report = asyncio.run(RunEngine(report_writer=ReportWriter(tmp_path / "reports")).execute(
        EngineRequest("incomplete", scenario, "lab-web"), provider=MockModelProvider(),
        client=ChangedClient(service), cancel_event=asyncio.Event(), emit=emit,
    ))
    assert report.verdict == "INCONCLUSIVE"
    assert report.scope_policy.revision == 1
    expected = {"missing": "SCOPE_METADATA_MISSING", "changed": "SCOPE_SNAPSHOT_MISMATCH",
                "finish-denied": "SCOPE_LIMIT_EXCEEDED"}[failure]
    assert any(expected in warning for warning in report.warnings)
    serialized = report.model_dump_json() + json.dumps(events)
    for raw in ("local-a-password", "local-b-password", "lab_session=", "Bearer ", "Ignore prior instructions"):
        assert raw not in serialized
