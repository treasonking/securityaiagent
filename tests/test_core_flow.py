from __future__ import annotations

import asyncio

import pytest

from common.schemas import Evidence, Verdict
from controller.engine import EngineRequest, RunCancelled, RunEngine
from controller.providers import MockModelProvider
from controller.reporting import ReportWriter
from controller.tool_clients import DirectToolClient
from tests.helpers import make_service
from verifier.core import verify_access_control
from worker.service import ToolService, WorkerLimits


def _run(tmp_path, mode: str):
    async def execute():
        service, _ = make_service(tmp_path, mode)
        emitted = []

        async def emit(event_type, payload):
            emitted.append((event_type, payload))

        report = await RunEngine(report_writer=ReportWriter(tmp_path / "reports")).execute(
            EngineRequest(run_id=f"run-{mode}", scenario_id="access-control", target_id="lab-web"),
            provider=MockModelProvider(),
            client=DirectToolClient(service),
            cancel_event=asyncio.Event(),
            emit=emit,
        )
        return report, emitted

    return asyncio.run(execute())


def test_vulnerable_core_flow_has_separate_candidate_and_verified_finding(tmp_path):
    report, emitted = _run(tmp_path, "vulnerable")
    assert report.verdict == Verdict.VULNERABLE
    assert len(report.finding_candidates) == 1
    assert len(report.verified_findings) == 1
    assert report.limits_used["http_requests"] == 11
    assert report.environment["target_server_log"] == "correlated"
    assert any(event == "evidence_added" for event, _ in emitted)
    evidence_file = tmp_path / "reports" / "run-vulnerable" / "evidence.json"
    assert evidence_file.exists()
    assert "Ignore prior instructions" not in evidence_file.read_text(encoding="utf-8")
    pending = [
        Evidence.model_validate(payload["evidence"])
        for event, payload in emitted
        if event == "evidence_added"
    ]
    for item in pending:
        item.server_observation = "target_log_offline_pending"
    assert verify_access_control(pending).verdict == Verdict.INCONCLUSIVE


def test_fixed_core_flow_is_blocked_by_access_control(tmp_path):
    report, _ = _run(tmp_path, "fixed")
    assert report.verdict == Verdict.BLOCKED_BY_ACCESS_CONTROL
    assert report.mode == "fixed"


def test_request_limit_failure_is_inconclusive_without_scope_expansion(tmp_path):
    async def execute():
        service, _ = make_service(tmp_path, "vulnerable", max_requests=2)

        async def emit(_event_type, _payload):
            return None

        return await RunEngine(report_writer=ReportWriter(tmp_path / "reports")).execute(
            EngineRequest(run_id="run-limit", scenario_id="access-control", target_id="lab-web"),
            provider=MockModelProvider(),
            client=DirectToolClient(service),
            cancel_event=asyncio.Event(),
            emit=emit,
        )

    report = asyncio.run(execute())
    assert report.verdict == Verdict.INCONCLUSIVE
    assert any("request limit" in item.lower() for item in report.warnings)


def test_cancellation_interrupts_provider_wait(tmp_path):
    class SlowProvider:
        mode = "mock"
        model_id = None

        async def propose_candidates(self, **_kwargs):
            await asyncio.sleep(30)

    async def execute():
        service, _ = make_service(tmp_path, "fixed")
        cancel = asyncio.Event()

        async def emit(_event_type, _payload):
            return None

        task = asyncio.create_task(
            RunEngine(report_writer=ReportWriter(tmp_path / "reports")).execute(
                EngineRequest(run_id="run-cancel-provider", scenario_id="access-control", target_id="lab-web"),
                provider=SlowProvider(),
                client=DirectToolClient(service),
                cancel_event=cancel,
                emit=emit,
            )
        )
        await asyncio.sleep(0)
        cancel.set()
        with pytest.raises(RunCancelled):
            await asyncio.wait_for(task, timeout=1)

    asyncio.run(execute())


def test_tool_call_limit_is_cumulative_for_a_run(tmp_path):
    async def execute():
        base, _ = make_service(tmp_path, "fixed")
        service = ToolService(
            policies=base.policies,
            accounts=base.accounts,
            limits=WorkerLimits(max_tool_calls=1, requests_per_second=0),
            transport=base.transport,
            observation_reader=base.observation_reader,
        )
        started = await service.start_session("run-tool-limit", "lab-web", "user-a")
        assert started.ok
        rejected = await service.list_own_documents(
            "run-tool-limit", "lab-web", started.data["session_ref"]
        )
        assert rejected.error_code == "POLICY_REJECTED"
        assert "tool call limit" in rejected.message

    asyncio.run(execute())
