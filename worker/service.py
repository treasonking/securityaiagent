from __future__ import annotations

import asyncio
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from common.sanitize import body_digest
from common.schemas import Evidence, ToolResult
from worker.policy import PolicyViolation, TargetPolicy


_MARKER = re.compile(r"^SYN-[A-Z]+-(?:PRIVATE-)?[0-9]{3}$")


@dataclass(frozen=True)
class WorkerLimits:
    max_requests: int = 30
    max_tool_calls: int = 12
    timeout_seconds: float = 5.0
    run_timeout_seconds: float = 180.0
    max_response_bytes: int = 65_536
    requests_per_second: float = 2.0
    max_concurrency: int = 1
    max_runs: int = 100
    state_ttl_seconds: float = 600.0

    def __post_init__(self) -> None:
        if (
            self.max_requests <= 0
            or self.max_tool_calls <= 0
            or self.max_concurrency <= 0
            or self.max_runs <= 0
        ):
            raise ValueError("request, tool, and concurrency limits must be positive")
        if (
            self.timeout_seconds <= 0
            or self.run_timeout_seconds <= 0
            or self.max_response_bytes <= 0
            or self.state_ttl_seconds <= 0
        ):
            raise ValueError("timeout and response-size limits must be positive")
        if self.requests_per_second < 0:
            raise ValueError("requests_per_second cannot be negative")


@dataclass
class _Session:
    account_ref: str
    cookies: httpx.Cookies


@dataclass
class _RunState:
    run_id: str
    started_monotonic: float
    request_count: int = 0
    tool_count: int = 0
    cancelled: bool = False
    finished: bool = False
    mode: str = "unknown"
    sessions: dict[str, _Session] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    last_request_monotonic: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    active_http_tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    ended_monotonic: float | None = None


class ToolService:
    """The only component allowed to turn a registered target into HTTP calls."""

    def __init__(
        self,
        *,
        policies: dict[str, TargetPolicy],
        accounts: dict[str, tuple[str, str]],
        limits: WorkerLimits | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        observation_reader: Callable[[str], dict[str, Any] | None] | None = None,
        account_ids: dict[str, str] | None = None,
    ) -> None:
        self.policies = policies
        self.accounts = accounts
        self.limits = limits or WorkerLimits()
        self.transport = transport
        self.observation_reader = observation_reader
        self.account_ids = account_ids or {
            "user-a": "acct-a",
            "user-b": "acct-b",
            "admin": "acct-admin",
        }
        self._runs: dict[str, _RunState] = {}
        self._runs_lock = asyncio.Lock()
        self._http_semaphore = asyncio.Semaphore(self.limits.max_concurrency)

    async def _state(self, run_id: str, *, create: bool = False) -> _RunState:
        if not run_id or len(run_id) > 128:
            raise PolicyViolation("invalid run_id")
        async with self._runs_lock:
            now = time.monotonic()
            expired = [
                key
                for key, item in self._runs.items()
                if item.ended_monotonic is not None
                and now - item.ended_monotonic >= self.limits.state_ttl_seconds
            ]
            for key in expired:
                self._runs.pop(key, None)
            state = self._runs.get(run_id)
            if state is None and create:
                if len(self._runs) >= self.limits.max_runs:
                    raise PolicyViolation("worker run queue limit exceeded")
                state = _RunState(run_id=run_id, started_monotonic=time.monotonic())
                self._runs[run_id] = state
            if state is None:
                raise PolicyViolation("run is not initialized")
            return state

    def _check_run(self, state: _RunState) -> None:
        if state.cancelled:
            raise PolicyViolation("run is cancelled")
        if state.finished:
            raise PolicyViolation("run is already finished")
        if time.monotonic() - state.started_monotonic > self.limits.run_timeout_seconds:
            state.cancelled = True
            state.cancel_event.set()
            state.ended_monotonic = time.monotonic()
            raise PolicyViolation("run timeout exceeded")
    def _count_tool(self, state: _RunState) -> None:
        self._check_run(state)
        if state.tool_count >= self.limits.max_tool_calls:
            state.cancelled = True
            state.cancel_event.set()
            state.ended_monotonic = time.monotonic()
            raise PolicyViolation("tool call limit exceeded")
        state.tool_count += 1

    def _run_seconds_remaining(self, state: _RunState) -> float:
        return self.limits.run_timeout_seconds - (time.monotonic() - state.started_monotonic)

    async def _wait_for_gate(
        self,
        state: _RunState,
        awaitable: Any,
        *,
        on_abandoned_success: Callable[[], None] | None = None,
    ) -> Any:
        self._check_run(state)
        operation = asyncio.ensure_future(awaitable)
        cancellation = asyncio.create_task(state.cancel_event.wait())
        transferred = False
        abandoned = False

        async def abandon_operation() -> None:
            nonlocal abandoned
            if transferred or abandoned:
                return
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            if (
                on_abandoned_success is not None
                and not operation.cancelled()
                and operation.exception() is None
            ):
                on_abandoned_success()
            abandoned = True

        try:
            done, _ = await asyncio.wait(
                {operation, cancellation},
                timeout=max(0.0, self._run_seconds_remaining(state)),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                state.cancelled = True
                state.cancel_event.set()
                state.ended_monotonic = time.monotonic()
                await abandon_operation()
                raise PolicyViolation("run timeout exceeded")
            if cancellation in done and state.cancel_event.is_set():
                await abandon_operation()
                raise PolicyViolation("run is cancelled")
            if operation in done:
                result = await operation
                transferred = True
                return result
            raise PolicyViolation("run wait ended unexpectedly")
        except BaseException:
            await abandon_operation()
            raise
        finally:
            cancellation.cancel()
            await asyncio.gather(cancellation, return_exceptions=True)

    async def _request(
        self,
        state: _RunState,
        policy: TargetPolicy,
        *,
        method: str,
        path: str,
        account_ref: str,
        cookies: httpx.Cookies | None = None,
        json: dict[str, str] | None = None,
    ) -> tuple[httpx.Response, str]:
        normalized = policy.normalize_relative_path(path)
        await self._wait_for_gate(
            state,
            self._http_semaphore.acquire(),
            on_abandoned_success=self._http_semaphore.release,
        )
        try:
            async with state.lock:
                self._check_run(state)
                interval = 1.0 / self.limits.requests_per_second if self.limits.requests_per_second > 0 else 0
                remaining = interval - (time.monotonic() - state.last_request_monotonic)
                if remaining > 0:
                    await self._wait_for_gate(state, asyncio.sleep(remaining))
                self._check_run(state)
                if state.request_count >= self.limits.max_requests:
                    state.cancelled = True
                    state.cancel_event.set()
                    state.ended_monotonic = time.monotonic()
                    raise PolicyViolation("HTTP request limit exceeded")
                request_id = str(uuid.uuid4())
                state.request_count += 1
                state.last_request_monotonic = time.monotonic()
            self._check_run(state)
            headers = {"X-SecurityLab-Run": state.run_id, "X-SecurityLab-Request": request_id}
            timeout_seconds = min(self.limits.timeout_seconds, self._run_seconds_remaining(state))
            if timeout_seconds <= 0:
                self._check_run(state)
                raise PolicyViolation("run timeout exceeded")
            timeout = httpx.Timeout(timeout_seconds)
            current_task = asyncio.current_task()
            if current_task is not None:
                state.active_http_tasks.add(current_task)
            async with httpx.AsyncClient(
                base_url=policy.base_url,
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
                cookies=cookies,
            ) as client:
                try:
                    async with asyncio.timeout(timeout_seconds):
                        async with client.stream(method, normalized, headers=headers, json=json) as streamed:
                            policy.assert_response_url(str(streamed.url))
                            if 300 <= streamed.status_code < 400:
                                raise PolicyViolation("redirect responses are never followed")
                            content_length = streamed.headers.get("content-length")
                            if content_length and int(content_length) > self.limits.max_response_bytes:
                                raise PolicyViolation("response exceeds configured byte limit")
                            body = bytearray()
                            async for chunk in streamed.aiter_bytes():
                                self._check_run(state)
                                if len(body) + len(chunk) > self.limits.max_response_bytes:
                                    raise PolicyViolation("response exceeds configured byte limit")
                                body.extend(chunk)
                            decoded_headers = [
                                (key, value)
                                for key, value in streamed.headers.multi_items()
                                if key.lower()
                                not in {"content-encoding", "content-length", "transfer-encoding"}
                            ]
                            decoded_headers.append(("content-length", str(len(body))))
                            response = httpx.Response(
                                streamed.status_code,
                                headers=decoded_headers,
                                content=bytes(body),
                                request=streamed.request,
                                extensions=streamed.extensions,
                            )
                except TimeoutError as exc:
                    if self._run_seconds_remaining(state) <= 0:
                        state.cancelled = True
                        state.cancel_event.set()
                        state.ended_monotonic = time.monotonic()
                        raise PolicyViolation("run timeout exceeded") from exc
                    raise PolicyViolation("HTTP request timeout exceeded") from exc
                finally:
                    if current_task is not None:
                        state.active_http_tasks.discard(current_task)
            return response, request_id
        finally:
            self._http_semaphore.release()

    @staticmethod
    def _error(run_id: str, exc: Exception) -> ToolResult:
        code = "POLICY_REJECTED" if isinstance(exc, PolicyViolation) else "TOOL_ERROR"
        return ToolResult(ok=False, run_id=run_id, error_code=code, message=str(exc))

    async def start_session(self, run_id: str, target_id: str, account_ref: str) -> ToolResult:
        try:
            state = await self._state(run_id, create=True)
            self._check_run(state)
            policy = self.policies.get(target_id)
            if policy is None:
                raise PolicyViolation("target_id is not registered")
            credentials = self.accounts.get(account_ref)
            if credentials is None:
                raise PolicyViolation("account_ref is not registered")
            self._count_tool(state)
            response, _ = await self._request(
                state,
                policy,
                method="POST",
                path="/login",
                account_ref=account_ref,
                json={"username": credentials[0], "password": credentials[1]},
            )
            if response.status_code != 200 or "lab_session" not in response.cookies:
                return ToolResult(
                    ok=False,
                    run_id=run_id,
                    error_code="AUTHENTICATION_FAILED",
                    message=f"synthetic account login returned {response.status_code}",
                )
            state.mode = response.headers.get("X-SecurityLab-Mode", "unknown")
            session_ref = f"sess_{secrets.token_urlsafe(24)}"
            state.sessions[session_ref] = _Session(account_ref=account_ref, cookies=response.cookies)
            return ToolResult(ok=True, run_id=run_id, data={"session_ref": session_ref, "authenticated": True})
        except Exception as exc:
            return self._error(run_id, exc)

    async def list_own_documents(self, run_id: str, target_id: str, session_ref: str) -> ToolResult:
        try:
            state = await self._state(run_id)
            self._check_run(state)
            policy = self.policies.get(target_id)
            if policy is None:
                raise PolicyViolation("target_id is not registered")
            session = state.sessions.get(session_ref)
            if session is None:
                raise PolicyViolation("unknown opaque session_ref")
            self._count_tool(state)
            response, _ = await self._request(
                state,
                policy,
                method="GET",
                path="/documents",
                account_ref=session.account_ref,
                cookies=session.cookies,
            )
            if response.status_code != 200:
                return ToolResult(
                    ok=False,
                    run_id=run_id,
                    error_code="SESSION_OR_TARGET_ERROR",
                    message=f"document list returned {response.status_code}",
                )
            document_ids = [item["document_id"] for item in response.json().get("documents", [])]
            return ToolResult(ok=True, run_id=run_id, data={"document_ids": document_ids})
        except Exception as exc:
            return self._error(run_id, exc)

    async def fetch_document(
        self,
        run_id: str,
        target_id: str,
        session_ref: str,
        document_id: str,
        purpose: str,
    ) -> ToolResult:
        try:
            state = await self._state(run_id)
            self._check_run(state)
            policy = self.policies.get(target_id)
            if policy is None:
                raise PolicyViolation("target_id is not registered")
            session = state.sessions.get(session_ref)
            if session is None:
                raise PolicyViolation("unknown opaque session_ref")
            path = policy.document_path(document_id)
            self._count_tool(state)
            response, request_id = await self._request(
                state,
                policy,
                method="GET",
                path=path,
                account_ref=session.account_ref,
                cookies=session.cookies,
            )
            marker = None
            if response.status_code == 200:
                payload = response.json()
                possible_marker = payload.get("marker")
                if isinstance(possible_marker, str) and _MARKER.fullmatch(possible_marker):
                    marker = possible_marker
            observation = self.observation_reader(request_id) if self.observation_reader else None
            correlated = bool(
                observation
                and observation.get("run_id") == run_id
                and observation.get("request_id") == request_id
                and observation.get("method") == "GET"
                and observation.get("path") == path
                and observation.get("status_code") == response.status_code
                and observation.get("account_id") == self.account_ids.get(session.account_ref)
                and observation.get("marker") == marker
            )
            evidence = Evidence(
                evidence_id=f"ev_{uuid.uuid4().hex}",
                run_id=run_id,
                method="GET",
                path=path,
                status_code=response.status_code,
                account_ref=session.account_ref,
                request_id=request_id,
                synthetic_document_marker=marker,
                body_hash=body_digest(response.content),
                server_observation="target_log_correlated" if correlated else "target_log_offline_pending",
                purpose=purpose,
            )
            state.evidence.append(evidence)
            return ToolResult(
                ok=True,
                run_id=run_id,
                data={"status_code": response.status_code, "marker": marker},
                evidence=evidence,
            )
        except Exception as exc:
            return self._error(run_id, exc)

    async def finish_run(self, run_id: str) -> ToolResult:
        try:
            state = await self._state(run_id)
            if state.cancelled:
                raise PolicyViolation("run is cancelled")
            self._count_tool(state)
            self._check_run(state)
            state.finished = True
            state.ended_monotonic = time.monotonic()
            state.sessions.clear()
            return ToolResult(
                ok=True,
                run_id=run_id,
                data={
                    "request_count": state.request_count,
                    "tool_count": state.tool_count,
                    "evidence_ids": [item.evidence_id for item in state.evidence],
                    "mode": state.mode if state.mode in {"vulnerable", "fixed"} else "unknown",
                },
            )
        except Exception as exc:
            return self._error(run_id, exc)

    async def cancel_run(self, run_id: str) -> ToolResult:
        try:
            state = await self._state(run_id)
            if state.finished:
                raise PolicyViolation("run is already finished")
            state.cancelled = True
            state.cancel_event.set()
            state.ended_monotonic = time.monotonic()
            state.sessions.clear()
            current = asyncio.current_task()
            active = [task for task in state.active_http_tasks if task is not current and not task.done()]
            for task in active:
                task.cancel()
            return ToolResult(ok=True, run_id=run_id, data={"cancelled": True})
        except Exception as exc:
            return self._error(run_id, exc)
