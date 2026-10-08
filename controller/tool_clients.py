from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Protocol

import httpx

from common.schemas import ToolResult
from worker.service import ToolService


class ToolClient(Protocol):
    transport_name: str

    @asynccontextmanager
    async def session(self) -> AsyncIterator[None]: ...

    async def list_tools(self) -> list[str]: ...
    async def start_session(self, run_id: str, target_id: str, account_ref: str) -> ToolResult: ...
    async def list_own_documents(self, run_id: str, target_id: str, session_ref: str) -> ToolResult: ...
    async def fetch_document(
        self, run_id: str, target_id: str, session_ref: str, document_id: str, purpose: str
    ) -> ToolResult: ...
    async def finish_run(self, run_id: str) -> ToolResult: ...
    async def cancel_run(self, run_id: str) -> ToolResult: ...


class DirectToolClient:
    transport_name = "function"

    def __init__(self, service: ToolService) -> None:
        self.service = service

    @asynccontextmanager
    async def session(self) -> AsyncIterator[None]:
        yield

    async def list_tools(self) -> list[str]:
        return ["start_session", "list_own_documents", "fetch_document", "finish_run"]

    async def start_session(self, run_id: str, target_id: str, account_ref: str) -> ToolResult:
        return await self.service.start_session(run_id, target_id, account_ref)

    async def list_own_documents(self, run_id: str, target_id: str, session_ref: str) -> ToolResult:
        return await self.service.list_own_documents(run_id, target_id, session_ref)

    async def fetch_document(
        self, run_id: str, target_id: str, session_ref: str, document_id: str, purpose: str
    ) -> ToolResult:
        return await self.service.fetch_document(run_id, target_id, session_ref, document_id, purpose)

    async def finish_run(self, run_id: str) -> ToolResult:
        return await self.service.finish_run(run_id)

    async def cancel_run(self, run_id: str) -> ToolResult:
        return await self.service.cancel_run(run_id)


class FunctionWorkerClient:
    transport_name = "function"

    def __init__(self, *, base_url: str, token: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.transport = transport

    @asynccontextmanager
    async def session(self) -> AsyncIterator[None]:
        yield

    async def list_tools(self) -> list[str]:
        return ["start_session", "list_own_documents", "fetch_document", "finish_run"]

    async def _post(self, path: str, payload: dict[str, Any]) -> ToolResult:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}"},
            follow_redirects=False,
            trust_env=False,
            timeout=10,
            transport=self.transport,
        ) as client:
            response = await client.post(path, json=payload)
        response.raise_for_status()
        return ToolResult.model_validate(response.json())

    async def start_session(self, run_id: str, target_id: str, account_ref: str) -> ToolResult:
        return await self._post(
            "/v1/tools/start-session", {"run_id": run_id, "target_id": target_id, "account_ref": account_ref}
        )

    async def list_own_documents(self, run_id: str, target_id: str, session_ref: str) -> ToolResult:
        return await self._post(
            "/v1/tools/list-own-documents",
            {"run_id": run_id, "target_id": target_id, "session_ref": session_ref},
        )

    async def fetch_document(
        self, run_id: str, target_id: str, session_ref: str, document_id: str, purpose: str
    ) -> ToolResult:
        return await self._post(
            "/v1/tools/fetch-document",
            {
                "run_id": run_id,
                "target_id": target_id,
                "session_ref": session_ref,
                "document_id": document_id,
                "purpose": purpose,
            },
        )

    async def finish_run(self, run_id: str) -> ToolResult:
        return await self._post("/v1/tools/finish-run", {"run_id": run_id})

    async def cancel_run(self, run_id: str) -> ToolResult:
        return await self._post("/v1/runs/cancel", {"run_id": run_id})


class MCPWorkerClient:
    """OpenAI Agents SDK-managed Streamable HTTP client for the private worker."""

    transport_name = "mcp"

    def __init__(self, *, server_url: str, token: str) -> None:
        from agents.mcp import MCPServerStreamableHttp

        self.server_url = server_url
        self.token = token
        self._server = MCPServerStreamableHttp(
            name="SecurityLab internal worker",
            params={
                "url": server_url,
                "headers": {"Authorization": f"Bearer {token}"},
                "timeout": 10,
            },
            cache_tools_list=True,
            max_retry_attempts=1,
            require_approval="never",
            use_structured_content=True,
        )
        self._connected = False

    @asynccontextmanager
    async def session(self) -> AsyncIterator[None]:
        async with self._server:
            self._connected = True
            try:
                yield
            finally:
                self._connected = False

    async def list_tools(self) -> list[str]:
        if not self._connected:
            raise RuntimeError("MCP session is not connected")
        return [tool.name for tool in await self._server.list_tools()]

    @staticmethod
    def _decode_result(result: Any) -> ToolResult:
        structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
        if isinstance(structured, dict):
            if set(structured) == {"result"} and isinstance(structured["result"], dict):
                structured = structured["result"]
            return ToolResult.model_validate(structured)
        for item in getattr(result, "content", []):
            text = getattr(item, "text", None)
            if text:
                return ToolResult.model_validate(json.loads(text))
        raise RuntimeError("MCP tool returned no decodable result")

    async def _call(self, name: str, payload: dict[str, Any]) -> ToolResult:
        if not self._connected:
            raise RuntimeError("MCP session is not connected")
        return self._decode_result(await self._server.call_tool(name, payload))

    async def start_session(self, run_id: str, target_id: str, account_ref: str) -> ToolResult:
        return await self._call(
            "start_session", {"run_id": run_id, "target_id": target_id, "account_ref": account_ref}
        )

    async def list_own_documents(self, run_id: str, target_id: str, session_ref: str) -> ToolResult:
        return await self._call(
            "list_own_documents", {"run_id": run_id, "target_id": target_id, "session_ref": session_ref}
        )

    async def fetch_document(
        self, run_id: str, target_id: str, session_ref: str, document_id: str, purpose: str
    ) -> ToolResult:
        return await self._call(
            "fetch_document",
            {
                "run_id": run_id,
                "target_id": target_id,
                "session_ref": session_ref,
                "document_id": document_id,
                "purpose": purpose,
            },
        )

    async def finish_run(self, run_id: str) -> ToolResult:
        return await self._call("finish_run", {"run_id": run_id})

    async def cancel_run(self, run_id: str) -> ToolResult:
        base_url = self.server_url.removesuffix("/mcp").rstrip("/")
        async with httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {self.token}"},
            follow_redirects=False,
            trust_env=False,
            timeout=10,
        ) as client:
            response = await client.post("/v1/runs/cancel", json={"run_id": run_id})
        response.raise_for_status()
        return ToolResult.model_validate(response.json())
