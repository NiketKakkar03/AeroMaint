"""MCP 2025-03-26 JSON-RPC transport and public HTTP adapter."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from services.mcp_server.server import McpDispatcher, PublicApiError, ToolContext, ToolError

PROTOCOL_VERSION = "2025-03-26"
RESOURCE_TEMPLATES = [
    {
        "uriTemplate": "aeromaint://sessions/{session_id}",
        "name": "Session manifest",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "aeromaint://sessions/{session_id}/streams",
        "name": "Session streams",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "aeromaint://sessions/{session_id}/model-track",
        "name": "Health model track",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "aeromaint://sessions/{session_id}/annotations",
        "name": "Session annotations",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "aeromaint://exports/{export_id}",
        "name": "Export job",
        "mimeType": "application/json",
    },
]


class HttpPublicApiClient:
    def __init__(self, base_url: str, *, timeout_seconds: float = 4.5) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        json_body: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        if method == "POST" and json_body is not None and "idempotency_key" in json_body:
            headers["Idempotency-Key"] = str(json_body.pop("idempotency_key"))
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout_seconds
            ) as client:
                response = await client.request(method, path, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            raise PublicApiError(503) from exc
        if response.status_code >= 400:
            raise PublicApiError(response.status_code)
        value = response.json()
        if not isinstance(value, dict):
            raise PublicApiError(502)
        return value


def _rpc_error(
    request_id: Any, code: int, message: str, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


class McpTransport:
    def __init__(self, dispatcher: McpDispatcher) -> None:
        self.dispatcher = dispatcher

    async def handle(self, message: Any, context: ToolContext) -> dict[str, Any] | None:
        if (
            not isinstance(message, dict)
            or message.get("jsonrpc") != "2.0"
            or not isinstance(message.get("method"), str)
        ):
            return _rpc_error(
                message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request"
            )
        request_id, method = message.get("id"), message["method"]
        if request_id is None:
            return None
        params = message.get("params", {})
        if not isinstance(params, dict):
            return _rpc_error(request_id, -32602, "Invalid params")
        try:
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "resources": {"listChanged": False},
                        },
                        "serverInfo": {"name": "aeromaint", "version": "0.1.0"},
                    },
                }
            if method == "ping":
                result: dict[str, Any] = {}
            elif method == "tools/list":
                result = {"tools": self.dispatcher.tool_descriptions()}
            elif method == "tools/call":
                name, arguments = params.get("name"), params.get("arguments", {})
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    return _rpc_error(request_id, -32602, "Invalid params")
                called = await self.dispatcher.call(name, arguments, context)
                result = {
                    "content": [
                        {"type": "text", "text": json.dumps(called, separators=(",", ":"))}
                    ],
                    "structuredContent": called,
                    "isError": False,
                }
            elif method == "resources/list":
                result = {"resources": []}
            elif method == "resources/templates/list":
                result = {"resourceTemplates": RESOURCE_TEMPLATES}
            elif method == "resources/read":
                result = await self._read_resource(params, context)
            else:
                return _rpc_error(request_id, -32601, "Method not found")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except ToolError as exc:
            return _rpc_error(request_id, -32000, "Tool call failed", exc.as_dict())

    async def _read_resource(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri.startswith("aeromaint://"):
            raise ToolError(
                "invalid_arguments", "Invalid resource URI", context.trace_id or "unknown"
            )
        parts = uri.removeprefix("aeromaint://").split("/")
        mapping: tuple[str, dict[str, Any]] | None = None
        if len(parts) == 2 and parts[0] == "sessions":
            mapping = ("sessions.get", {"session_id": parts[1]})
        elif len(parts) == 3 and parts[0] == "sessions" and parts[2] == "streams":
            mapping = ("streams.list", {"session_id": parts[1]})
        elif len(parts) == 3 and parts[0] == "sessions" and parts[2] == "model-track":
            mapping = ("model_tracks.get", {"session_id": parts[1]})
        elif len(parts) == 3 and parts[0] == "sessions" and parts[2] == "annotations":
            mapping = ("annotations.list", {"session_id": parts[1]})
        elif len(parts) == 2 and parts[0] == "exports":
            mapping = ("exports.get", {"export_id": parts[1]})
        if mapping is None:
            raise ToolError("not_found", "Resource not found", context.trace_id or "unknown")
        value = await self.dispatcher.call(mapping[0], mapping[1], context)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(value, separators=(",", ":")),
                }
            ]
        }


def create_app(dispatcher: McpDispatcher) -> FastAPI:
    app = FastAPI(title="AeroMaint MCP", docs_url=None, redoc_url=None)
    transport = McpTransport(dispatcher)

    @app.post("/mcp")
    async def mcp(
        request: Request,
        authorization: str | None = Header(default=None),
        x_user_id: str | None = Header(default=None),
        x_permissions: str = Header(default=""),
        x_trace_id: str | None = Header(default=None),
    ) -> JSONResponse:
        if not authorization or not authorization.startswith("Bearer ") or not x_user_id:
            return JSONResponse(
                _rpc_error(None, -32001, "Authentication required"), status_code=401
            )
        try:
            message = await request.json()
        except Exception:
            return JSONResponse(_rpc_error(None, -32700, "Parse error"), status_code=400)
        result = await transport.handle(
            message,
            ToolContext(
                x_user_id,
                authorization[7:],
                x_trace_id,
                frozenset(filter(None, (item.strip() for item in x_permissions.split(",")))),
            ),
        )
        return JSONResponse(result or {}, status_code=202 if result is None else 200)

    return app


async def run_stdio(transport: McpTransport, context: ToolContext) -> None:
    while line := await asyncio.to_thread(sys.stdin.readline):
        response: dict[str, Any] | None
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = _rpc_error(None, -32700, "Parse error")
        else:
            response = await transport.handle(message, context)
        if response is not None:
            print(json.dumps(response, separators=(",", ":")), flush=True)


def main() -> None:
    client = HttpPublicApiClient(os.getenv("AEROMAINT_API_URL", "http://127.0.0.1:8000"))
    context = ToolContext(
        os.environ["AEROMAINT_MCP_USER_ID"],
        os.environ["AEROMAINT_MCP_TOKEN"],
        permissions=frozenset(filter(None, os.getenv("AEROMAINT_MCP_PERMISSIONS", "").split(","))),
    )
    asyncio.run(run_stdio(McpTransport(McpDispatcher(client)), context))


if __name__ == "__main__":
    main()
