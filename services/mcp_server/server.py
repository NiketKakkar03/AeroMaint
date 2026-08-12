"""Typed, bounded MCP boundary over AeroMaint's public HTTP API."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote, urlencode
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

LOGGER = logging.getLogger("aeromaint.mcp")
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
MAX_NS = 9_223_372_036_854_775_807


class PublicApiError(RuntimeError):
    """Sanitized failure returned by a public API adapter."""

    def __init__(self, status: int, code: str = "upstream_error") -> None:
        super().__init__(code)
        self.status = status
        self.code = code


class PublicApiClient(Protocol):
    async def request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        json_body: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...


class ToolError(RuntimeError):
    def __init__(self, code: str, message: str, trace_id: str) -> None:
        super().__init__(message)
        self.code = code
        self.trace_id = trace_id

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self), "trace_id": self.trace_id}


@dataclass(frozen=True, slots=True)
class ToolContext:
    user_id: str
    bearer_token: str
    trace_id: str | None = None
    permissions: frozenset[str] = frozenset()


class StrictArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmptyArguments(StrictArguments):
    pass


class PageArguments(StrictArguments):
    cursor: str | None = Field(default=None, min_length=1, max_length=512)
    limit: int = Field(default=20, ge=1, le=100)


class SessionArguments(StrictArguments):
    session_id: str = Field(pattern=ID_PATTERN)


class SessionPageArguments(SessionArguments, PageArguments):
    pass


class StreamArguments(SessionArguments):
    stream_id: str = Field(pattern=ID_PATTERN)


class EngineArguments(StrictArguments):
    engine_id: str = Field(pattern=ID_PATTERN)


class SearchArguments(StrictArguments):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class SeekArguments(StreamArguments):
    timestamp_ns: int = Field(ge=0, le=MAX_NS)


class AnnotationDraftArguments(SessionArguments):
    start_ns: int = Field(ge=0, le=MAX_NS)
    end_ns: int = Field(gt=0, le=MAX_NS)
    body: str = Field(min_length=1, max_length=4000)
    stream_id: str | None = Field(default=None, pattern=ID_PATTERN)

    @model_validator(mode="after")
    def ordered_range(self) -> AnnotationDraftArguments:
        if self.end_ns <= self.start_ns:
            raise ValueError("end_ns must be greater than start_ns")
        return self


class ExportArguments(SessionArguments):
    start_ns: int = Field(ge=0, le=MAX_NS)
    end_ns: int = Field(gt=0, le=MAX_NS)
    stream_ids: list[str] = Field(default_factory=list, max_length=64)
    include_annotations: bool = True
    sensor_format: str = Field(default="parquet", pattern=r"^(parquet|csv)$")
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def valid_export(self) -> ExportArguments:
        if self.end_ns <= self.start_ns:
            raise ValueError("end_ns must be greater than start_ns")
        if len(set(self.stream_ids)) != len(self.stream_ids):
            raise ValueError("stream_ids must be unique")
        if any(not re.fullmatch(ID_PATTERN, item) for item in self.stream_ids):
            raise ValueError("stream_ids contains a malformed ID")
        return self


class ExportIdArguments(StrictArguments):
    export_id: str = Field(pattern=ID_PATTERN)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    arguments: type[StrictArguments]
    method: str
    path: Callable[[Any], str]
    body: Callable[[Any], dict[str, Any] | None] = lambda _args: None
    required_permission: str | None = None


def _page(path: str, args: PageArguments) -> str:
    query: dict[str, Any] = {"limit": args.limit}
    if args.cursor is not None:
        query["cursor"] = args.cursor
    return f"{path}?{urlencode(query)}"


def _seek_path(args: SeekArguments) -> str:
    base = (
        f"/v1/sessions/{quote(args.session_id, safe='')}/streams/"
        f"{quote(args.stream_id, safe='')}/frame-at"
    )
    return f"{base}?{urlencode({'time_ns': args.timestamp_ns, 'mode': 'nearest'})}"


TOOLS: dict[str, ToolDefinition] = {
    "sessions.list": ToolDefinition(
        "sessions.list",
        "List visible capture sessions",
        PageArguments,
        "GET",
        lambda a: _page("/v1/sessions", a),
    ),
    "sessions.get": ToolDefinition(
        "sessions.get",
        "Read a session manifest",
        SessionArguments,
        "GET",
        lambda a: f"/v1/sessions/{quote(a.session_id, safe='')}/manifest",
    ),
    "streams.list": ToolDefinition(
        "streams.list",
        "List streams in a session",
        SessionPageArguments,
        "GET",
        lambda a: _page(f"/v1/sessions/{quote(a.session_id, safe='')}/streams", a),
    ),
    "model_tracks.get": ToolDefinition(
        "model_tracks.get",
        "Read a session health-model track",
        SessionArguments,
        "GET",
        lambda a: f"/v1/health/sessions/{quote(a.session_id, safe='')}/model-track",
    ),
    "predictions.get": ToolDefinition(
        "predictions.get",
        "Read current engine predictions",
        EngineArguments,
        "GET",
        lambda a: f"/v1/health/engines/{quote(a.engine_id, safe='')}",
    ),
    "documents.search": ToolDefinition(
        "documents.search",
        "Search cited maintenance documents",
        SearchArguments,
        "GET",
        lambda a: f"/v1/documents/search?{urlencode({'q': a.query, 'limit': a.limit})}",
    ),
    "seek_events.lookup": ToolDefinition(
        "seek_events.lookup",
        "Find the frame nearest a session timestamp",
        SeekArguments,
        "GET",
        _seek_path,
    ),
    "annotations.list": ToolDefinition(
        "annotations.list",
        "List session annotations",
        SessionArguments,
        "GET",
        lambda a: f"/v1/sessions/{quote(a.session_id, safe='')}/annotations",
    ),
    "annotations.create_draft": ToolDefinition(
        "annotations.create_draft",
        "Create a draft annotation",
        AnnotationDraftArguments,
        "POST",
        lambda a: f"/v1/sessions/{quote(a.session_id, safe='')}/annotations",
        lambda a: {
            **a.model_dump(exclude={"session_id", "body"}),
            "kind": "note",
            "payload": {"body": a.body},
        },
        "annotation:draft",
    ),
    "exports.get": ToolDefinition(
        "exports.get",
        "Read export job status",
        ExportIdArguments,
        "GET",
        lambda a: f"/v1/exports/{quote(a.export_id, safe='')}",
    ),
    "exports.create": ToolDefinition(
        "exports.create",
        "Create a synchronized export job",
        ExportArguments,
        "POST",
        lambda _a: "/v1/exports",
        lambda a: a.model_dump(),
        "export:create",
    ),
}


class McpDispatcher:
    """Validate, authorize, trace, and bound calls to public service interfaces."""

    def __init__(
        self,
        client: PublicApiClient,
        *,
        timeout_seconds: float = 5.0,
        max_output_bytes: int = 64_000,
        failure_injector: Callable[[str], None] | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_output_bytes <= 0:
            raise ValueError("budgets must be positive")
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.failure_injector = failure_injector

    @property
    def tools(self) -> tuple[str, ...]:
        return tuple(TOOLS)

    def tool_descriptions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "description": item.description,
                "inputSchema": item.arguments.model_json_schema(),
            }
            for item in TOOLS.values()
        ]

    async def call(
        self, name: str, arguments: Mapping[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        trace_id = context.trace_id or str(uuid4())
        try:
            definition = TOOLS[name]
            parsed = definition.arguments.model_validate(dict(arguments))
        except ValidationError as exc:
            raise ToolError(
                "invalid_arguments", "Tool arguments failed schema validation", trace_id
            ) from exc
        except KeyError as exc:
            raise ToolError(
                "unknown_tool", f"Unknown or prohibited tool: {name}", trace_id
            ) from exc
        if not context.user_id or not context.bearer_token:
            raise ToolError("unauthenticated", "Caller identity is required", trace_id)
        if (
            definition.required_permission
            and definition.required_permission not in context.permissions
        ):
            raise ToolError("permission_denied", "Caller lacks the required permission", trace_id)
        if self.failure_injector:
            try:
                self.failure_injector(name)
            except Exception as exc:
                raise ToolError(
                    "upstream_unavailable", "Public API is unavailable", trace_id
                ) from exc
        LOGGER.info(
            "mcp_call_started",
            extra={"trace_id": trace_id, "tool": name, "user_id": context.user_id},
        )
        try:
            result = await asyncio.wait_for(
                self.client.request(
                    definition.method,
                    definition.path(parsed),
                    token=context.bearer_token,
                    json_body=definition.body(parsed),
                    trace_id=trace_id,
                ),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            raise ToolError(
                "timeout", "Public API call exceeded its time budget", trace_id
            ) from exc
        except PublicApiError as exc:
            code = {
                401: "unauthenticated",
                403: "permission_denied",
                404: "not_found",
                409: "conflict",
                422: "invalid_arguments",
            }.get(exc.status, "upstream_error")
            raise ToolError(code, "Public API rejected the request", trace_id) from exc
        except Exception as exc:
            raise ToolError("upstream_unavailable", "Public API is unavailable", trace_id) from exc
        encoded = json.dumps(result, separators=(",", ":"), ensure_ascii=False).encode()
        if len(encoded) > self.max_output_bytes:
            raise ToolError("output_too_large", "Tool result exceeded its output budget", trace_id)
        LOGGER.info(
            "mcp_call_finished",
            extra={"trace_id": trace_id, "tool": name, "output_bytes": len(encoded)},
        )
        return {"trace_id": trace_id, "user_id": context.user_id, "result": result}
