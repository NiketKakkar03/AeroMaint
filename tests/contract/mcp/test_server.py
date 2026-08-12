import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.mcp_server import (
    McpDispatcher,
    McpTransport,
    PublicApiError,
    ToolContext,
    ToolError,
    create_app,
)


class RecordingClient:
    def __init__(
        self, result: dict[str, Any] | None = None, delay: float = 0, error: Exception | None = None
    ) -> None:
        self.result = result or {"ok": True}
        self.delay = delay
        self.error = error
        self.calls: list[tuple[str, str, str, dict[str, Any] | None, str | None]] = []

    async def request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        json_body: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        await asyncio.sleep(self.delay)
        self.calls.append((method, path, token, json_body, trace_id))
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_calls_public_interface_and_propagates_identity_and_trace() -> None:
    client = RecordingClient({"session_id": "s-1"})
    result = await McpDispatcher(client).call(
        "sessions.get", {"session_id": "s-1"}, ToolContext("engineer-1", "secret", "trace-1")
    )
    assert result == {
        "trace_id": "trace-1",
        "user_id": "engineer-1",
        "result": {"session_id": "s-1"},
    }
    assert client.calls == [("GET", "/v1/sessions/s-1/manifest", "secret", None, "trace-1")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,args",
    [
        ("sessions.get", {"session_id": "../secret"}),
        ("seek_events.lookup", {"session_id": "s", "stream_id": "cam", "timestamp_ns": -1}),
        ("documents.search", {"query": "x", "limit": 11}),
        (
            "annotations.create_draft",
            {"session_id": "s", "start_ns": 20, "end_ns": 10, "body": "bad"},
        ),
        (
            "exports.create",
            {
                "session_id": "s",
                "start_ns": 0,
                "end_ns": 1,
                "stream_ids": ["../x"],
                "idempotency_key": "12345678",
            },
        ),
    ],
)
async def test_strict_schema_rejects_malformed_ids_ranges_and_arguments(
    name: str, args: dict[str, Any]
) -> None:
    with pytest.raises(ToolError) as malformed:
        await McpDispatcher(RecordingClient()).call(
            name,
            args,
            ToolContext("user", "token", "trace", frozenset({"annotation:draft", "export:create"})),
        )
    assert malformed.value.code == "invalid_arguments"


@pytest.mark.asyncio
async def test_rejects_approval_and_other_unlisted_high_risk_tools() -> None:
    for name in ("recommendations.approve", "annotations.review", "exports.cancel"):
        with pytest.raises(ToolError) as prohibited:
            await McpDispatcher(RecordingClient()).call(
                name, {}, ToolContext("user", "token", "trace")
            )
        assert prohibited.value.code == "unknown_tool"


@pytest.mark.asyncio
async def test_permission_gate_and_caller_token_propagate_to_mutation() -> None:
    client = RecordingClient()
    dispatcher = McpDispatcher(client)
    args = {"session_id": "s-1", "start_ns": 10, "end_ns": 20, "body": "Inspect"}
    with pytest.raises(ToolError) as denied:
        await dispatcher.call(
            "annotations.create_draft", args, ToolContext("viewer", "viewer-token")
        )
    assert denied.value.code == "permission_denied"
    await dispatcher.call(
        "annotations.create_draft",
        args,
        ToolContext("analyst", "caller-token", permissions=frozenset({"annotation:draft"})),
    )
    assert client.calls[0][2] == "caller-token"
    assert client.calls[0][3] == {
        "start_ns": 10,
        "end_ns": 20,
        "stream_id": None,
        "kind": "note",
        "payload": {"body": "Inspect"},
    }


@pytest.mark.asyncio
async def test_timeout_output_failure_injection_and_safe_upstream_errors() -> None:
    context = ToolContext("user", "token", "trace-budget")
    with pytest.raises(ToolError) as timed_out:
        await McpDispatcher(RecordingClient(delay=0.05), timeout_seconds=0.001).call(
            "predictions.get", {"engine_id": "ENG-1"}, context
        )
    assert (timed_out.value.code, timed_out.value.trace_id) == ("timeout", "trace-budget")
    with pytest.raises(ToolError) as oversized:
        await McpDispatcher(RecordingClient({"data": "x" * 100}), max_output_bytes=20).call(
            "documents.search", {"query": "bearing"}, context
        )
    assert oversized.value.code == "output_too_large"
    with pytest.raises(ToolError) as injected:
        await McpDispatcher(
            RecordingClient(),
            failure_injector=lambda _name: (_ for _ in ()).throw(
                RuntimeError("secret database detail")
            ),
        ).call("sessions.get", {"session_id": "s"}, context)
    assert str(injected.value) == "Public API is unavailable"
    with pytest.raises(ToolError) as forbidden:
        await McpDispatcher(RecordingClient(error=PublicApiError(403, "internal-secret"))).call(
            "sessions.get", {"session_id": "s"}, context
        )
    assert (forbidden.value.code, str(forbidden.value)) == (
        "permission_denied",
        "Public API rejected the request",
    )


@pytest.mark.asyncio
async def test_golden_initialize_list_call_and_resource_scenario() -> None:
    transport = McpTransport(McpDispatcher(RecordingClient({"id": "s-1"})))
    context = ToolContext("user", "token", "golden")
    initialized = await transport.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26"},
        },
        context,
    )
    assert initialized and initialized["result"]["protocolVersion"] == "2025-03-26"
    listed = await transport.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, context)
    names = {tool["name"] for tool in listed["result"]["tools"]}  # type: ignore[index]
    assert {
        "sessions.get",
        "streams.list",
        "model_tracks.get",
        "seek_events.lookup",
        "exports.create",
    } <= names
    called = await transport.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "sessions.get", "arguments": {"session_id": "s-1"}},
        },
        context,
    )
    assert json.loads(called["result"]["content"][0]["text"])["trace_id"] == "golden"  # type: ignore[index]
    resource = await transport.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/read",
            "params": {"uri": "aeromaint://sessions/s-1"},
        },
        context,
    )
    assert resource["result"]["contents"][0]["mimeType"] == "application/json"  # type: ignore[index]


def test_http_transport_requires_identity_and_serves_json_rpc() -> None:
    client = TestClient(create_app(McpDispatcher(RecordingClient())))
    message = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    assert client.post("/mcp", json=message).status_code == 401
    response = client.post(
        "/mcp",
        json=message,
        headers={
            "Authorization": "Bearer caller-token",
            "X-User-ID": "analyst",
            "X-Permissions": "session:read,annotation:draft",
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "aeromaint"
