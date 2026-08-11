import asyncio
from typing import Any

import pytest
from services.mcp_server import McpDispatcher, ToolContext, ToolError


class RecordingClient:
    def __init__(self, result: dict[str, Any] | None = None, delay: float = 0) -> None:
        self.result = result or {"ok": True}
        self.delay = delay
        self.calls: list[tuple[str, str, str, dict[str, Any] | None]] = []

    async def request(
        self, method: str, path: str, *, token: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        await asyncio.sleep(self.delay)
        self.calls.append((method, path, token, json_body))
        return self.result


@pytest.mark.asyncio
async def test_calls_public_interface_and_propagates_identity() -> None:
    client = RecordingClient({"session_id": "s-1"})
    dispatcher = McpDispatcher(client)
    result = await dispatcher.call(
        "sessions.get", {"session_id": "s-1"}, ToolContext("engineer-1", "secret", "trace-1")
    )
    assert result == {
        "trace_id": "trace-1",
        "user_id": "engineer-1",
        "result": {"session_id": "s-1"},
    }
    assert client.calls == [("GET", "/v1/sessions/s-1/manifest", "secret", None)]


@pytest.mark.asyncio
async def test_rejects_malformed_arguments_and_approval_tools() -> None:
    dispatcher = McpDispatcher(RecordingClient())
    context = ToolContext("user", "token", "trace")
    with pytest.raises(ToolError, match="session_id") as malformed:
        await dispatcher.call("sessions.get", {"session_id": "../secret"}, context)
    assert malformed.value.code == "invalid_arguments"
    with pytest.raises(ToolError, match="prohibited") as prohibited:
        await dispatcher.call("recommendations.approve", {}, context)
    assert prohibited.value.code == "unknown_tool"


@pytest.mark.asyncio
async def test_timeout_and_output_budgets_have_safe_errors() -> None:
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


@pytest.mark.asyncio
async def test_mutations_are_drafts_and_forward_the_caller_token() -> None:
    client = RecordingClient()
    dispatcher = McpDispatcher(client)
    await dispatcher.call(
        "annotations.create_draft",
        {"session_id": "s-1", "start_ns": "10", "end_ns": "20", "body": "Inspect"},
        ToolContext("analyst", "caller-token"),
    )
    assert client.calls[0][2] == "caller-token"
    assert client.calls[0][3] == {"start_ns": "10", "end_ns": "20", "body": "Inspect"}
