"""Typed MCP tool boundary over AeroMaint's public API client."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class PublicApiClient(Protocol):
    async def request(
        self, method: str, path: str, *, token: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


class ToolError(RuntimeError):
    def __init__(self, code: str, message: str, trace_id: str) -> None:
        super().__init__(message)
        self.code = code
        self.trace_id = trace_id


@dataclass(frozen=True, slots=True)
class ToolContext:
    user_id: str
    bearer_token: str
    trace_id: str | None = None


class StrictArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionArguments(StrictArguments):
    session_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class EngineArguments(StrictArguments):
    engine_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SearchArguments(StrictArguments):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class AnnotationDraftArguments(SessionArguments):
    start_ns: str = Field(pattern=r"^-?\d+$")
    end_ns: str = Field(pattern=r"^-?\d+$")
    body: str = Field(min_length=1, max_length=4000)


class ExportArguments(SessionArguments):
    start_ns: str = Field(pattern=r"^-?\d+$")
    end_ns: str = Field(pattern=r"^-?\d+$")


class McpDispatcher:
    """Validate and bound MCP calls without exposing storage or approval operations."""

    def __init__(
        self,
        client: PublicApiClient,
        *,
        timeout_seconds: float = 5.0,
        max_output_bytes: int = 64_000,
    ) -> None:
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    @property
    def tools(self) -> tuple[str, ...]:
        return (
            "sessions.get",
            "predictions.get",
            "documents.search",
            "annotations.create_draft",
            "exports.create",
        )

    async def call(
        self, name: str, arguments: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        trace_id = context.trace_id or str(uuid4())
        try:
            request = self._request(name, arguments)
        except ValidationError as exc:
            raise ToolError("invalid_arguments", str(exc), trace_id) from exc
        except KeyError as exc:
            raise ToolError(
                "unknown_tool", f"Unknown or prohibited tool: {name}", trace_id
            ) from exc
        method, path, body = request
        try:
            result = await asyncio.wait_for(
                self.client.request(method, path, token=context.bearer_token, json_body=body),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            raise ToolError("timeout", "Public API call exceeded its budget", trace_id) from exc
        encoded = json.dumps(result, separators=(",", ":")).encode()
        if len(encoded) > self.max_output_bytes:
            raise ToolError("output_too_large", "Tool result exceeded its output budget", trace_id)
        return {"trace_id": trace_id, "user_id": context.user_id, "result": result}

    def _request(
        self, name: str, arguments: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any] | None]:
        if name == "sessions.get":
            session = SessionArguments.model_validate(arguments)
            return "GET", f"/v1/sessions/{session.session_id}/manifest", None
        if name == "predictions.get":
            engine = EngineArguments.model_validate(arguments)
            return "GET", f"/v1/health/engines/{engine.engine_id}", None
        if name == "documents.search":
            search = SearchArguments.model_validate(arguments)
            return "GET", f"/v1/documents/search?q={search.query}&limit={search.limit}", None
        if name == "annotations.create_draft":
            annotation = AnnotationDraftArguments.model_validate(arguments)
            body = annotation.model_dump(exclude={"session_id"})
            return "POST", f"/v1/sessions/{annotation.session_id}/annotations", body
        if name == "exports.create":
            export = ExportArguments.model_validate(arguments)
            body = {**export.model_dump(exclude={"session_id"}), "kind": "synchronized_range"}
            return "POST", f"/v1/sessions/{export.session_id}/exports", body
        raise KeyError(name)
