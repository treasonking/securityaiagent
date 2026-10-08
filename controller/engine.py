from __future__ import annotations

import asyncio
import platform
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from common.schemas import Evidence, ModelUsage, RunReport, RunStatus, ToolResult, Verdict, utc_now
from controller.providers import ModelProvider
from controller.reporting import ReportWriter
from controller.tool_clients import ToolClient
from verifier.core import verify_access_control


EventCallback = Callable[[str, dict[str, object]], Awaitable[None]]


class RunCancelled(Exception):
    pass


class ToolExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineRequest:
    run_id: str
    scenario_id: str
    target_id: str


class RunEngine:
    def __init__(self, *, report_writer: ReportWriter) -> None:
        self.report_writer = report_writer

    @staticmethod
    async def _check_cancel(cancel_event: asyncio.Event, client: ToolClient, run_id: str) -> None:
        if cancel_event.is_set():
            await client.cancel_run(run_id)
            raise RunCancelled("run cancellation requested")

    @staticmethod
    def _required(result: ToolResult, operation: str) -> ToolResult:
        if not result.ok:
            raise ToolExecutionError(f"{operation}: {result.error_code or 'UNKNOWN'}: {result.message or ''}")
        return result

    async def execute(
        self,
        request: EngineRequest,
        *,
        provider: ModelProvider,
        client: ToolClient,
        cancel_event: asyncio.Event,
        emit: EventCallback,
    ) -> RunReport:
        started_at = utc_now()
        evidence: list[Evidence] = []
        warnings: list[str] = []
        model_usage = ModelUsage()
        candidates = []
        mode = "unknown"
        limits_used: dict[str, int | float] = {"http_requests": 0, "tool_calls": 0}

        try:
            provider_task = asyncio.create_task(
                provider.propose_candidates(scenario_id=request.scenario_id, target_id=request.target_id)
            )
            cancellation_task = asyncio.create_task(cancel_event.wait())
            done, _ = await asyncio.wait(
                {provider_task, cancellation_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if cancellation_task in done and cancel_event.is_set():
                provider_task.cancel()
                await asyncio.gather(provider_task, return_exceptions=True)
                raise RunCancelled("run cancellation requested during provider call")
            cancellation_task.cancel()
            await asyncio.gather(cancellation_task, return_exceptions=True)
            provider_result = await provider_task
            candidates = provider_result.candidates
            model_usage = provider_result.usage
        except RunCancelled:
            raise
        except Exception as exc:
            if provider.mode == "openai":
                raise RuntimeError(f"live model run is not verified: {type(exc).__name__}") from exc
            warnings.append(f"mock provider failed: {type(exc).__name__}")

        async def invoke(name: str, call: Callable[[], Awaitable[ToolResult]]) -> ToolResult:
            await self._check_cancel(cancel_event, client, request.run_id)
            await emit("tool_started", {"tool": name})
            result = await call()
            await emit("tool_finished", {"tool": name, "ok": result.ok, "error_code": result.error_code})
            if result.evidence:
                evidence.append(result.evidence)
                await emit(
                    "evidence_added",
                    {
                        "evidence_id": result.evidence.evidence_id,
                        "purpose": result.evidence.purpose,
                        "status_code": result.evidence.status_code,
                        "evidence": result.evidence.model_dump(mode="json"),
                    },
                )
            return result

        try:
            async with client.session():
                discovered = set(await client.list_tools())
                required_tools = {"start_session", "list_own_documents", "fetch_document", "finish_run"}
                if discovered != required_tools:
                    raise ToolExecutionError(
                        f"worker tool allowlist mismatch: expected {sorted(required_tools)}, got {sorted(discovered)}"
                    )

                sessions: dict[str, str] = {}
                for account_ref in ("user-a", "user-b", "admin"):
                    result = self._required(
                        await invoke(
                            "start_session",
                            lambda account_ref=account_ref: client.start_session(
                                request.run_id, request.target_id, account_ref
                            ),
                        ),
                        f"start_session({account_ref})",
                    )
                    sessions[account_ref] = str(result.data["session_ref"])

                documents: dict[str, list[str]] = {}
                for account_ref in ("user-a", "user-b", "admin"):
                    result = self._required(
                        await invoke(
                            "list_own_documents",
                            lambda account_ref=account_ref: client.list_own_documents(
                                request.run_id, request.target_id, sessions[account_ref]
                            ),
                        ),
                        f"list_own_documents({account_ref})",
                    )
                    documents[account_ref] = [str(item) for item in result.data.get("document_ids", [])]
                    if not documents[account_ref]:
                        raise ToolExecutionError(f"control account {account_ref} has no published document fixture")

                fetch_plan = (
                    ("user-a", documents["user-a"][0], "safe-own-a"),
                    ("user-b", documents["user-b"][0], "safe-own-b"),
                    ("admin", documents["admin"][0], "safe-admin"),
                    ("user-a", documents["user-b"][0], "attack-cross-b"),
                    ("user-a", "doc-missing-999", "edge-missing"),
                )
                for account_ref, document_id, purpose in fetch_plan:
                    self._required(
                        await invoke(
                            "fetch_document",
                            lambda account_ref=account_ref, document_id=document_id, purpose=purpose: client.fetch_document(
                                request.run_id,
                                request.target_id,
                                sessions[account_ref],
                                document_id,
                                purpose,
                            ),
                        ),
                        f"fetch_document({purpose})",
                    )

                finish = self._required(
                    await invoke("finish_run", lambda: client.finish_run(request.run_id)), "finish_run"
                )
                mode_value = finish.data.get("mode")
                mode = str(mode_value) if mode_value in {"vulnerable", "fixed"} else "unknown"
                limits_used = {
                    "http_requests": int(finish.data.get("request_count", 0)),
                    "tool_calls": int(finish.data.get("tool_count", 0)),
                }
        except RunCancelled:
            raise
        except Exception as exc:
            warnings.append(f"tool workflow incomplete: {type(exc).__name__}: {exc}")

        verification = verify_access_control(evidence)
        warnings.extend(verification.warnings)
        recommendations = {
            Verdict.VULNERABLE: [
                "Enforce owner-or-admin authorization on the document detail query.",
                "Restart the target in fixed mode, reset synthetic state, and rerun the identical scenario.",
            ],
            Verdict.BLOCKED_BY_ACCESS_CONTROL: [
                "Retain the owner-or-admin authorization regression test.",
                "Correlate the target-local log before using the result as external evidence.",
            ],
            Verdict.INCONCLUSIVE: [
                "Resolve the recorded control or transport failure and rerun without expanding scope."
            ],
        }[verification.verdict]
        report = RunReport(
            run_id=request.run_id,
            scenario_id=request.scenario_id,
            target_id=request.target_id,
            mode=mode,
            provider_mode=provider.mode,
            model_id=provider.model_id,
            tool_transport=client.transport_name,
            started_at=started_at,
            finished_at=utc_now(),
            status=RunStatus.COMPLETED,
            verdict=verification.verdict,
            finding_candidates=candidates,
            verified_findings=verification.findings,
            evidence_ids=[item.evidence_id for item in evidence],
            limits_used=limits_used,
            model_usage=model_usage,
            warnings=warnings,
            environment={
                "python": platform.python_version(),
                "platform": platform.system(),
                "target_data": "synthetic-only",
                "target_server_log": "correlated" if evidence and all(
                    item.server_observation == "target_log_correlated" for item in evidence
                ) else "offline-pending",
            },
            recommendations=recommendations,
        )
        self.report_writer.write(report, evidence)
        return report
