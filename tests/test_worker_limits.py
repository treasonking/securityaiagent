from __future__ import annotations

import asyncio
import gzip
import json
import zlib

import httpx
import pytest

from tests.helpers import make_service
from worker.policy import TargetPolicy
from worker.service import ToolService, WorkerLimits


class CountingStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.read_count = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            self.read_count += 1
            yield chunk

    async def aclose(self) -> None:
        return None


class OversizedTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.stream = CountingStream([b"x" * 64 for _ in range(16)])

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Set-Cookie": "lab_session=test; Path=/", "X-SecurityLab-Mode": "fixed"},
            stream=self.stream,
            request=request,
        )


class BlockingTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.request_count = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.request_count += 1
        self.started.set()
        await self.release.wait()
        return httpx.Response(
            200,
            headers={"Set-Cookie": "lab_session=test; Path=/", "X-SecurityLab-Mode": "fixed"},
            json={"status": "authenticated"},
            request=request,
        )


class LoginTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.request_count = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.request_count += 1
        return httpx.Response(
            200,
            headers={"Set-Cookie": "lab_session=test; Path=/", "X-SecurityLab-Mode": "fixed"},
            json={"status": "authenticated"},
            request=request,
        )


class CompressedDocumentTransport(httpx.AsyncBaseTransport):
    def __init__(self, encoding: str, *, document_id: str = "doc-a-001") -> None:
        self.encoding = encoding
        self.document_id = document_id
        self.compressed_length = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login":
            return httpx.Response(
                200,
                headers={"Set-Cookie": "lab_session=test; Path=/", "X-SecurityLab-Mode": "fixed"},
                json={"status": "authenticated"},
                request=request,
            )
        body = json.dumps({"documents": [{"document_id": self.document_id}]}).encode()
        encoded = gzip.compress(body) if self.encoding == "gzip" else zlib.compress(body)
        self.compressed_length = len(encoded)
        return httpx.Response(
            200,
            headers={
                "Content-Encoding": self.encoding,
                "Content-Length": str(len(encoded)),
            },
            content=encoded,
            request=request,
        )


def _service(transport: httpx.AsyncBaseTransport, **limit_overrides) -> ToolService:
    return ToolService(
        policies={
            "lab-web": TargetPolicy("lab-web", "http", "10.78.0.30", 8080)
        },
        accounts={"user-a": ("user_a", "local-a-password")},
        limits=WorkerLimits(requests_per_second=0, **limit_overrides),
        transport=transport,
    )


def test_response_limit_stops_stream_before_full_download():
    transport = OversizedTransport()

    async def exercise():
        result = await _service(transport, max_response_bytes=128).start_session(
            "run-size", "lab-web", "user-a"
        )
        assert not result.ok
        assert result.error_code == "POLICY_REJECTED"
        assert "byte limit" in (result.message or "")

    asyncio.run(exercise())
    assert transport.stream.read_count == 3


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
def test_compressed_json_is_decoded_once(encoding):
    async def exercise():
        transport = CompressedDocumentTransport(encoding)
        service = _service(transport, max_response_bytes=1024)
        started = await service.start_session(f"run-{encoding}", "lab-web", "user-a")
        assert started.ok
        listed = await service.list_own_documents(
            f"run-{encoding}", "lab-web", started.data["session_ref"]
        )
        assert listed.ok
        assert listed.data["document_ids"] == ["doc-a-001"]

    asyncio.run(exercise())


def test_compressed_response_enforces_decoded_byte_limit():
    async def exercise():
        transport = CompressedDocumentTransport("gzip", document_id="doc-" + "a" * 512)
        service = _service(transport, max_response_bytes=128)
        started = await service.start_session("run-compressed-cap", "lab-web", "user-a")
        assert started.ok
        result = await service.list_own_documents(
            "run-compressed-cap", "lab-web", started.data["session_ref"]
        )
        assert transport.compressed_length < 128
        assert not result.ok
        assert result.error_code == "POLICY_REJECTED"
        assert "byte limit" in (result.message or "")

    asyncio.run(exercise())


@pytest.mark.parametrize("max_requests", [1, 11])
def test_http_request_cap_allows_exactly_n_requests(max_requests):
    async def exercise():
        transport = LoginTransport()
        service = _service(
            transport,
            max_requests=max_requests,
            max_tool_calls=max_requests + 1,
        )
        for index in range(max_requests):
            result = await service.start_session("run-cap", "lab-web", "user-a")
            assert result.ok, f"request {index + 1} should be allowed"
        rejected = await service.start_session("run-cap", "lab-web", "user-a")
        assert not rejected.ok
        assert rejected.error_code == "POLICY_REJECTED"
        assert "request limit" in (rejected.message or "")
        assert transport.request_count == max_requests

    asyncio.run(exercise())


def test_cancel_during_rate_limit_wait_sends_no_additional_request(tmp_path):
    async def exercise():
        base, _ = make_service(tmp_path, "fixed")
        service = ToolService(
            policies=base.policies,
            accounts=base.accounts,
            limits=WorkerLimits(requests_per_second=0.5),
            transport=base.transport,
            observation_reader=base.observation_reader,
        )
        started = await service.start_session("run-rate", "lab-web", "user-a")
        state = await service._state("run-rate")
        waiting = asyncio.create_task(
            service.list_own_documents(
                "run-rate", "lab-web", started.data["session_ref"]
            )
        )
        await asyncio.sleep(0.05)
        cancelled = await service.cancel_run("run-rate")
        result = await waiting
        assert cancelled.ok
        assert not result.ok
        assert state.request_count == 1

    asyncio.run(exercise())


def test_cancel_during_semaphore_wait_never_enters_transport():
    async def exercise():
        transport = BlockingTransport()
        service = _service(transport, max_concurrency=1)
        holder = asyncio.create_task(service.start_session("run-holder", "lab-web", "user-a"))
        await transport.started.wait()
        waiting = asyncio.create_task(service.start_session("run-wait", "lab-web", "user-a"))
        await asyncio.sleep(0)
        assert (await service.cancel_run("run-wait")).ok
        rejected = await waiting
        assert not rejected.ok
        assert transport.request_count == 1
        transport.release.set()
        assert (await holder).ok

    asyncio.run(exercise())


@pytest.mark.parametrize("release_first", [False, True])
def test_external_task_cancellation_does_not_leak_semaphore_slot(release_first):
    async def exercise():
        transport = LoginTransport()
        service = _service(transport, max_concurrency=1)
        await service._http_semaphore.acquire()
        waiting = asyncio.create_task(service.start_session("run-abandoned", "lab-web", "user-a"))
        await asyncio.sleep(0)
        assert not waiting.done()
        loop = asyncio.get_running_loop()
        first, second = (
            (service._http_semaphore.release, waiting.cancel)
            if release_first
            else (waiting.cancel, service._http_semaphore.release)
        )
        loop.call_soon(first)
        loop.call_soon(second)
        result = await asyncio.gather(waiting, return_exceptions=True)
        assert isinstance(result[0], asyncio.CancelledError)

        completed = await asyncio.wait_for(
            service.start_session("run-after-cancel", "lab-web", "user-a"),
            timeout=1,
        )
        assert completed.ok
        assert transport.request_count == 1

    asyncio.run(exercise())


def test_cancel_aborts_inflight_http_task():
    async def exercise():
        transport = BlockingTransport()
        service = _service(transport)
        active = asyncio.create_task(service.start_session("run-active", "lab-web", "user-a"))
        await transport.started.wait()
        assert (await service.cancel_run("run-active")).ok
        result = await asyncio.gather(active, return_exceptions=True)
        assert isinstance(result[0], asyncio.CancelledError)
        assert transport.request_count == 1

    asyncio.run(exercise())
