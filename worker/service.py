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

    def __post_init__(self) -> None:
        if self.max_requests <= 0 or self.max_tool_calls <= 0 or self.max_concurrency <= 0:
            raise ValueError("request, tool, and concurrency limits must be positive")
        if self.timeout_seconds <= 0 or self.run_timeout_seconds <= 0 or self.max_response_bytes <= 0:
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
    ) -> None:
        self.policies = policies
        self.accounts = accounts
        self.limits = limits or WorkerLimits()
        self.transport = transport
        self.observation_reader = observation_reader
        self._runs: dict[str, _RunState] = {}
        self._runs_lock = asyncio.Lock()
        self._http_semaphore = asyncio.Semaphore(self.limits.max_concurrency)

    async def _state(self, run_id: str, *, create: bool = False) -> _RunState:
        if not run_id or len(run_id) > 128:
            raise PolicyViolation("invalid run_id")
        async with self._runs_lock:
            state = self._runs.get(run_id)
            if state is None and create:
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
            raise PolicyViolation("run timeout exceeded")
        if state.request_count >= self.limits.max_requests:
            state.cancelled = True
            raise PolicyViolation("HTTP request limit exceeded")

    def _count_tool(self, state: _RunState) -> None:
        self._check_run(state)
        if state.tool_count >= self.limits.max_tool_calls:
            state.cancelled = True
            raise PolicyViolation("tool call limit exceeded")
        state.tool_count += 1

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
        async with state.lock:
            self._check_run(state)
            interval = 1.0 / self.limits.requests_per_second if self.limits.requests_per_second > 0 else 0
            remaining = interval - (time.monotonic() - state.last_request_monotonic)
            if remaining > 0:
                await asyncio.sleep(remaining)
            request_id = str(uuid.uuid4())
            state.request_count += 1
            state.last_request_monotonic = time.monotonic()
        headers = {"X-SecurityLab-Run": state.run_id, "X-SecurityLab-Request": request_id}
        timeout = httpx.Timeout(self.limits.timeout_seconds)
        async with self._http_semaphore:
            async with httpx.AsyncClient(
                base_url=policy.base_url,
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
                cookies=cookies,
            ) as client:
                response = await client.request(method, normalized, headers=headers, json=json)
        policy.assert_response_url(str(response.url))
        if 300 <= response.status_code < 400:
            raise PolicyViolation("redirect responses are never followed")
        if len(response.content) > self.limits.max_response_bytes:
            raise PolicyViolation("response exceeds configured byte limit")
        return response, request_id

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
                and observation.get("request_id") == request_id
                and observation.get("status_code") == response.status_code
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
            state.finished = True
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
            state.cancelled = True
            state.sessions.clear()
            return ToolResult(ok=True, run_id=run_id, data={"cancelled": True})
        except Exception as exc:
            return self._error(run_id, exc)
