from __future__ import annotations

import asyncio
from dataclasses import dataclass

from common.schemas import Evidence, RunStatus
from controller.engine import EngineRequest, RunCancelled, RunEngine
from controller.providers import get_provider
from controller.repository import Repository
from controller.tool_clients import ToolClient


@dataclass(frozen=True)
class ManagerSettings:
    max_concurrency: int = 1
    model_id: str | None = None
    model_max_calls: int = 8


class RunManager:
    def __init__(
        self,
        *,
        repository: Repository,
        engine: RunEngine,
        clients: dict[str, ToolClient],
        settings: ManagerSettings | None = None,
    ) -> None:
        self.repository = repository
        self.engine = engine
        self.clients = clients
        self.settings = settings or ManagerSettings()
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrency)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}

    def submit(
        self,
        *,
        run_id: str,
        scenario_id: str,
        target_id: str,
        provider_mode: str,
        tool_transport: str,
    ) -> None:
        cancel_event = asyncio.Event()
        self._cancel_events[run_id] = cancel_event
        self.repository.append_event(run_id, "queued", {"scenario_id": scenario_id, "target_id": target_id})
        task = asyncio.create_task(
            self._run(
                run_id=run_id,
                scenario_id=scenario_id,
                target_id=target_id,
                provider_mode=provider_mode,
                tool_transport=tool_transport,
                cancel_event=cancel_event,
            ),
            name=f"securitylab-{run_id}",
        )
        self._tasks[run_id] = task

    async def _run(
        self,
        *,
        run_id: str,
        scenario_id: str,
        target_id: str,
        provider_mode: str,
        tool_transport: str,
        cancel_event: asyncio.Event,
    ) -> None:
        try:
            async with self._semaphore:
                if cancel_event.is_set():
                    raise RunCancelled("cancelled while queued")
                self.repository.update_run_status(run_id, RunStatus.RUNNING)
                self.repository.append_event(run_id, "running", {"transport": tool_transport})
                provider = get_provider(
                    provider_mode,
                    model_id=self.settings.model_id,
                    max_turns=self.settings.model_max_calls,
                )
                client = self.clients[tool_transport]

                async def emit(event_type: str, payload: dict[str, object]) -> None:
                    event_payload = dict(payload)
                    raw_evidence = event_payload.pop("evidence", None)
                    if isinstance(raw_evidence, dict):
                        self.repository.save_evidence(Evidence.model_validate(raw_evidence))
                    self.repository.append_event(run_id, event_type, event_payload)

                report = await self.engine.execute(
                    EngineRequest(run_id=run_id, scenario_id=scenario_id, target_id=target_id),
                    provider=provider,
                    client=client,
                    cancel_event=cancel_event,
                    emit=emit,
                )
                self.repository.save_findings(report)
                self.repository.update_run_status(run_id, RunStatus.COMPLETED, report=report)
                self.repository.append_event(
                    run_id,
                    "report_ready",
                    {"verdict": report.verdict, "evidence_count": len(report.evidence_ids)},
                )
        except RunCancelled:
            self.repository.update_run_status(run_id, RunStatus.CANCELLED)
            self.repository.append_event(run_id, "cancelled", {"reason": "user_requested"})
        except asyncio.CancelledError:
            self.repository.update_run_status(run_id, RunStatus.INTERRUPTED, error_message="controller shutdown")
            raise
        except Exception as exc:
            self.repository.update_run_status(run_id, RunStatus.FAILED, error_message=f"{type(exc).__name__}: {exc}")
            self.repository.append_event(run_id, "failed", {"error": type(exc).__name__})
        finally:
            self._cancel_events.pop(run_id, None)
            self._tasks.pop(run_id, None)

    async def cancel(self, run_id: str, tool_transport: str) -> None:
        event = self._cancel_events.get(run_id)
        if event is not None:
            event.set()
        client = self.clients.get(tool_transport)
        if client is not None:
            try:
                await client.cancel_run(run_id)
            except Exception:
                pass

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
