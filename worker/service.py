from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from common.api_contract import ApiAdapter, select
from common.sanitize import body_digest
from common.schemas import Evidence, HttpObservation, ScenarioId, ToolResult
from worker.policy import PolicyViolation, TargetPolicy
from worker.limits import WorkerLimits
from worker.registry import ScopeRegistry, load_scope_registry
from worker.scope import ScopeSnapshot, ScopeViolation
from worker.candidate_policy import CONTRACT


_MARKER = re.compile(r"^SYN-[A-Z]+-(?:PRIVATE-)?[0-9]{3}$")


@dataclass
class _Session:
    account_ref: str
    cookies: httpx.Cookies
    target_id: str
    bearer: str | None = field(default=None, repr=False)


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
    scenario_id: ScenarioId = "access-control"
    target_id: str | None = None
    scope: ScopeSnapshot | None = None
    failed: bool = False
    candidate_snapshot: str | None = None


class ToolService:
    """The only component allowed to turn a registered target into HTTP calls."""

    def __init__(
        self,
        *,
        policies: dict[str, TargetPolicy] | None = None,
        registry: ScopeRegistry | None = None,
        accounts: dict[str, tuple[str, str]],
        limits: WorkerLimits | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        observation_reader: Callable[[str], dict[str, Any] | None] | None = None,
        account_ids: dict[str, str] | None = None,
    ) -> None:
        self.registry = registry if registry is not None else load_scope_registry()
        if policies is not None:
            self.registry = self.registry.with_test_origins(policies)
        self.policies = dict(self.registry.policies)
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
        self._http_semaphore = asyncio.Semaphore(min(
            self.limits.max_concurrency,
            *(self.registry.profile(key).limits.max_concurrency for key in self.registry.policies),
        ))

    async def _state(self, run_id: str, *, create: bool = False, scope: ScopeSnapshot | None = None,
                     candidate_snapshot: str | None = None) -> _RunState:
        if not run_id or len(run_id) > 128:
            raise PolicyViolation("invalid run_id")
        async with self._runs_lock:
            now = time.monotonic()
            expired = [
                key
                for key, item in self._runs.items()
                if item.ended_monotonic is not None
                and now - item.ended_monotonic >= item.scope.limits.state_ttl_seconds
            ]
            for key in expired:
                self._runs.pop(key, None)
            state = self._runs.get(run_id)
            if state is None and create:
                if scope is None:
                    raise ScopeViolation("SCOPE_INVALID", "run requires a scope snapshot")
                if len(self._runs) >= scope.limits.max_runs:
                    raise ScopeViolation("SCOPE_LIMIT_EXCEEDED", "worker run queue limit exceeded")
                state = _RunState(run_id=run_id, started_monotonic=time.monotonic(), scope=scope,
                                  target_id=scope.target.target_id, scenario_id=scope.scenario_id,
                                  candidate_snapshot=candidate_snapshot)
                self._runs[run_id] = state
            if state is None:
                raise PolicyViolation("run is not initialized")
            if create and state.candidate_snapshot != candidate_snapshot:
                raise ScopeViolation('CANDIDATE_BINDING_REQUIRED', 'run policy binding cannot change')
            return state

    def _check_run(self, state: _RunState) -> None:
        if state.cancelled:
            raise PolicyViolation("run is cancelled")
        if state.finished:
            raise PolicyViolation("run is already finished")
        if state.failed:
            raise ScopeViolation("SCOPE_RUN_FAILED", "run has a prior policy or transport failure")
        if time.monotonic() - state.started_monotonic > state.scope.limits.run_timeout_seconds:
            state.cancelled = True
            state.cancel_event.set()
            state.ended_monotonic = time.monotonic()
            raise ScopeViolation("SCOPE_LIMIT_EXCEEDED", "run timeout exceeded")
    def _count_tool(self, state: _RunState) -> None:
        self._check_run(state)
        maximum = state.scope.limits.max_tool_calls
        if state.tool_count >= maximum:
            state.cancelled = True
            state.cancel_event.set()
            state.ended_monotonic = time.monotonic()
            raise ScopeViolation("SCOPE_LIMIT_EXCEEDED", "tool call limit exceeded")
        state.tool_count += 1

    def _run_seconds_remaining(self, state: _RunState) -> float:
        return state.scope.limits.run_timeout_seconds - (time.monotonic() - state.started_monotonic)

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
                raise ScopeViolation("SCOPE_LIMIT_EXCEEDED", "run timeout exceeded")
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
        operation: str,
        method: str,
        path: str,
        account_ref: str,
        session_ref: str | None = None,
        cookies: httpx.Cookies | None = None,
        json: dict[str, str] | None = None,
    ) -> tuple[httpx.Response, str]:
        def authorize():
            self._authorize_request(state, policy, operation, method, path, account_ref, session_ref, cookies, json)
        authorize()
        normalized = policy.normalize_relative_path(path)
        await self._wait_for_gate(
            state,
            self._http_semaphore.acquire(),
            on_abandoned_success=self._http_semaphore.release,
        )
        try:
            async with state.lock:
                self._check_run(state)
                interval = 1.0 / state.scope.limits.requests_per_second if state.scope.limits.requests_per_second > 0 else 0
                remaining = interval - (time.monotonic() - state.last_request_monotonic)
                if remaining > 0:
                    await self._wait_for_gate(state, asyncio.sleep(remaining))
                self._check_run(state)
                authorize()
                maximum = state.scope.limits.max_requests
                if state.request_count >= maximum:
                    state.cancelled = True
                    state.cancel_event.set()
                    state.ended_monotonic = time.monotonic()
                    raise ScopeViolation("SCOPE_LIMIT_EXCEEDED", "HTTP request limit exceeded")
                request_id = str(uuid.uuid4())
                state.request_count += 1
                state.last_request_monotonic = time.monotonic()
            self._check_run(state)
            headers = {"X-SecurityLab-Run": state.run_id, "X-SecurityLab-Request": request_id}
            if session_ref is not None and state.sessions[session_ref].bearer is not None:
                headers["Authorization"] = "Bearer " + state.sessions[session_ref].bearer
            timeout_seconds = min(state.scope.limits.timeout_seconds, self._run_seconds_remaining(state))
            if timeout_seconds <= 0:
                self._check_run(state)
                raise ScopeViolation("SCOPE_LIMIT_EXCEEDED", "run timeout exceeded")
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
                        authorize()
                        async with client.stream(method, normalized, headers=headers, json=json) as streamed:
                            policy.assert_response_url(str(streamed.url))
                            if 300 <= streamed.status_code < 400:
                                raise PolicyViolation("redirect responses are never followed")
                            content_length = streamed.headers.get("content-length")
                            if content_length and int(content_length) > state.scope.limits.max_response_bytes:
                                raise ScopeViolation("SCOPE_LIMIT_EXCEEDED", "response exceeds configured byte limit")
                            body = bytearray()
                            async for chunk in streamed.aiter_bytes():
                                self._check_run(state)
                                if len(body) + len(chunk) > state.scope.limits.max_response_bytes:
                                    raise ScopeViolation("SCOPE_LIMIT_EXCEEDED", "response exceeds configured byte limit")
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
                        raise ScopeViolation("SCOPE_LIMIT_EXCEEDED", "run timeout exceeded") from exc
                    raise ScopeViolation("SCOPE_LIMIT_EXCEEDED", "HTTP request timeout exceeded") from exc
                finally:
                    if current_task is not None:
                        state.active_http_tasks.discard(current_task)
            return response, request_id
        finally:
            self._http_semaphore.release()

    def _authorize_request(self, state, policy, operation, method, path, account_ref, session_ref, cookies, payload):
        if state.scope is None or state.scenario_id != state.scope.scenario_id or state.target_id != state.scope.target.target_id:
            raise ScopeViolation("SCOPE_SESSION_DENIED", "run identity differs from its scope snapshot")
        state.scope.authorize_request(policy, account_ref, operation, method, path)
        if operation == "login":
            credentials = self.accounts.get(account_ref)
            if (session_ref is not None or cookies is not None or credentials is None
                    or payload != state.scope.adapter.login_payload(credentials)):
                raise ScopeViolation("SCOPE_SESSION_DENIED", "login must use worker-owned credentials")
        else:
            session = state.sessions.get(session_ref)
            if (session is None or session.target_id != policy.target_id or session.account_ref != account_ref
                    or cookies is not session.cookies or payload is not None):
                raise ScopeViolation("SCOPE_SESSION_DENIED", "request is not bound to the run account session")

    def _result(self, state: _RunState, **kwargs) -> ToolResult:
        data = kwargs.pop("data", {})
        return ToolResult(run_id=state.run_id, scope_policy=state.scope.record(),
                          data={**data, "request_count": state.request_count, "tool_count": state.tool_count}, **kwargs)

    def _error(self, run_id: str, exc: Exception) -> ToolResult:
        code = exc.code if isinstance(exc, ScopeViolation) else "POLICY_REJECTED" if isinstance(exc, PolicyViolation) else "TOOL_ERROR"
        kwargs = dict(ok=False, error_code=code,
                      message=str(exc) if isinstance(exc, PolicyViolation) else type(exc).__name__)
        state = self._runs.get(run_id)
        if state is not None:
            state.failed = True
            state.ended_monotonic = state.ended_monotonic or time.monotonic()
            state.sessions.clear()
            return self._result(state, **kwargs)
        return ToolResult(run_id=run_id, **kwargs)

    async def start_session(self, run_id: str, target_id: str, account_ref: str,
                            scenario_id: ScenarioId = "access-control", *,
                            expected_snapshot_sha256: str | None = None,
                            candidate_contract: str | None = None) -> ToolResult:
        try:
            existing = self._runs.get(run_id)
            scope = existing.scope if existing else self.registry.snapshot(target_id, scenario_id, self.limits)
            if expected_snapshot_sha256 is not None or candidate_contract is not None:
                if (candidate_contract != CONTRACT or scenario_id != 'access-control-http'
                        or not isinstance(expected_snapshot_sha256, str)
                        or not re.fullmatch(r'[0-9a-f]{64}', expected_snapshot_sha256)):
                    raise ScopeViolation('CANDIDATE_BINDING_REQUIRED', 'candidate policy binding is invalid')
                if expected_snapshot_sha256 != scope.snapshot_sha256:
                    raise ScopeViolation('CANDIDATE_POLICY_CHANGED', 'worker snapshot differs from preview')
            if existing and existing.candidate_snapshot != expected_snapshot_sha256:
                raise ScopeViolation('CANDIDATE_BINDING_REQUIRED', 'run policy binding cannot change')
            if scope.target.target_id != target_id or scope.scenario_id != scenario_id:
                raise ScopeViolation("SCOPE_SESSION_DENIED", "run target or scenario mismatch")
            scope.authorize(account_ref, "login")
            state = await self._state(run_id, create=True, scope=scope, candidate_snapshot=expected_snapshot_sha256)
            self._check_run(state)
            if state.scope != scope:
                raise ScopeViolation("SCOPE_SESSION_DENIED", "concurrent run scope mismatch")
            policy = state.scope.target
            credentials = self.accounts.get(account_ref)
            if credentials is None:
                raise ScopeViolation("SCOPE_ACCOUNT_DENIED", "worker account credentials are not configured")
            self._count_tool(state)
            response, _ = await self._request(
                state,
                policy,
                operation="login",
                method="POST",
                path=scope.adapter.routes.login_path,
                account_ref=account_ref,
                json=scope.adapter.login_payload(credentials),
            )
            adapter = scope.adapter
            auth_value = None
            if response.status_code == 200:
                if adapter.auth_mode == "cookie":
                    auth_value = response.cookies.get(adapter.cookie_name)
                else:
                    auth_value = select(self._json_object(response), adapter.token_field)
            if not isinstance(auth_value, str) or not re.fullmatch(r"[A-Za-z0-9._~-]{1,2048}", auth_value):
                state.failed = True
                state.ended_monotonic = time.monotonic()
                state.sessions.clear()
                return self._result(state,
                    ok=False,
                    error_code="AUTHENTICATION_FAILED",
                    message=f"synthetic account login returned {response.status_code}",
                )
            if state.scenario_id == "access-control":
                state.mode = response.headers.get("X-SecurityLab-Mode", "unknown")
            session_ref = f"sess_{secrets.token_urlsafe(24)}"
            cookies = httpx.Cookies({adapter.cookie_name: auth_value}) if adapter.auth_mode == "cookie" else httpx.Cookies()
            state.sessions[session_ref] = _Session(account_ref=account_ref, cookies=cookies, target_id=target_id,
                                                  bearer=auth_value if adapter.auth_mode == "bearer" else None)
            return self._result(state, ok=True, data={"session_ref": session_ref, "authenticated": True})
        except Exception as exc:
            return self._error(run_id, exc)

    async def list_own_documents(self, run_id: str, target_id: str, session_ref: str) -> ToolResult:
        try:
            state = await self._state(run_id)
            self._check_run(state)
            policy = state.scope.target
            if policy.target_id != target_id:
                raise ScopeViolation("SCOPE_TARGET_DENIED", "target differs from the run snapshot")
            session = state.sessions.get(session_ref)
            if session is None or session.target_id != target_id:
                raise ScopeViolation("SCOPE_SESSION_DENIED", "unknown opaque session_ref")
            self._count_tool(state)
            response, request_id = await self._request(
                state,
                policy,
                operation="list_own_documents",
                method="GET",
                path=state.scope.adapter.routes.list_path,
                account_ref=session.account_ref,
                session_ref=session_ref,
                cookies=session.cookies,
            )
            if response.status_code != 200:
                state.failed = True
                state.ended_monotonic = time.monotonic()
                state.sessions.clear()
                return self._result(state,
                    ok=False,
                    error_code="SESSION_OR_TARGET_ERROR",
                    message=f"document list returned {response.status_code}",
                )
            adapter = state.scope.adapter
            payload = self._json_object(response)
            items = select(payload, adapter.list_field)
            if not isinstance(items, list) or len(items) > 100:
                raise PolicyViolation("invalid bounded document list")
            document_ids = [select(item, adapter.list_id_field) for item in items]
            for document_id in document_ids:
                adapter.routes.detail(document_id)
            if len(document_ids) != len(set(document_ids)):
                raise PolicyViolation("ambiguous document list")
            evidence = None
            if state.scenario_id == "access-control-http":
                expected = self.account_ids[session.account_ref]
                if select(payload, adapter.list_account_field) != expected or any(select(item, adapter.list_owner_field) != expected for item in items):
                    raise PolicyViolation("document list account or ownership is unverified")
                observation = self._http_metadata(response, session, session_ref, state.scope.adapter)
                observation.listed_document_ids = document_ids
                observation.owner_ref = session.account_ref
                observation.response_kind = "document_list"
                evidence = self._http_evidence(state, response, request_id, session, adapter.routes.list_path,
                                               "http-list-" + session.account_ref, observation)
            return self._result(state, ok=True, data={"document_ids": document_ids}, evidence=evidence)
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
            policy = state.scope.target
            if policy.target_id != target_id:
                raise ScopeViolation("SCOPE_TARGET_DENIED", "target differs from the run snapshot")
            session = state.sessions.get(session_ref)
            if session is None or session.target_id != target_id:
                raise ScopeViolation("SCOPE_SESSION_DENIED", "unknown opaque session_ref")
            path = state.scope.adapter.routes.detail(document_id)
            if state.scenario_id == "access-control-http" and purpose not in {
                "http-own-a", "http-own-b", "http-cross-b", "http-recheck-b", "http-recheck-a"
            }:
                raise PolicyViolation("HTTP evidence purpose is not registered")
            self._count_tool(state)
            response, request_id = await self._request(
                state,
                policy,
                operation="fetch_document",
                method="GET",
                path=path,
                account_ref=session.account_ref,
                session_ref=session_ref,
                cookies=session.cookies,
            )
            if state.scenario_id == "access-control-http":
                observation = self._http_metadata(response, session, session_ref, state.scope.adapter)
                evidence = self._http_evidence(state, response, request_id, session, path, purpose, observation)
                return self._result(state, ok=True, data={"status_code": response.status_code}, evidence=evidence)
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
            return self._result(state,
                ok=True,
                data={"status_code": response.status_code, "marker": marker},
                evidence=evidence,
            )
        except Exception as exc:
            return self._error(run_id, exc)

    @staticmethod
    def _json_object(response):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate response field")
                result[key] = value
            return result
        payload = json.loads(response.content, object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite response")))
        if not isinstance(payload, dict):
            raise ValueError("expected a JSON object")
        return payload

    def _http_metadata(self, response: httpx.Response, session: _Session, session_ref: str, adapter: ApiAdapter) -> HttpObservation:
        account_map = {self.account_ids[name]: name for name in ("user-a", "user-b")}
        observation = HttpObservation(
            session_binding=body_digest(session_ref.encode()), routes=adapter.routes,
            authenticated_account=account_map.get(response.headers.get(adapter.identity_header)),
        )
        try:
            payload = self._json_object(response)
        except (ValueError, UnicodeError):
            return observation
        # Denials must contain exactly the configured nested error object. A generic
        # error/HTML/login/public body cannot establish access-control blocking.
        denial = adapter.denial_value
        for key in reversed(adapter.denial_field.split(".")):
            denial = {key: denial}
        if response.status_code in {403, 404} and payload == denial:
            observation.response_kind = "document_denied"
        observation.canary_present = (select(payload, adapter.content_container_field) is not None
                                      or select(payload, adapter.legacy_marker_field) is not None)
        document_id = select(payload, adapter.resource_id_field)
        if isinstance(document_id, str) and re.fullmatch(r"doc-[a-z]+-[0-9]{3}", document_id):
            observation.document_id = document_id
        owner = select(payload, adapter.owner_field)
        observation.owner_ref = account_map.get(owner) if isinstance(owner, str) else None
        visibility = select(payload, adapter.visibility_field)
        content = select(payload, adapter.content_field)
        if (type(visibility) is type(adapter.private_value) and visibility == adapter.private_value
                and select(payload, adapter.content_kind_field) == adapter.content_kind_value
                and isinstance(content, str) and re.fullmatch(r"SYN-[A-Za-z0-9_-]{8,96}", content)):
            observation.private_canary_digest = body_digest(content.encode())
            observation.response_kind = "private_document"
        return observation

    @staticmethod
    def _http_evidence(state: _RunState, response: httpx.Response, request_id: str,
                       session: _Session, path: str, purpose: str, observation: HttpObservation) -> Evidence:
        evidence = Evidence(
            evidence_id=f"ev_{uuid.uuid4().hex}", run_id=state.run_id, method="GET", path=path,
            status_code=response.status_code, account_ref=session.account_ref, request_id=request_id,
            body_hash=body_digest(response.content), server_observation="http_observation",
            purpose=purpose, http_observation=observation,
        )
        state.evidence.append(evidence)
        return evidence

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
            return self._result(state,
                ok=True,
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
            return self._result(state, ok=True, data={"cancelled": True})
        except Exception as exc:
            return self._error(run_id, exc)
