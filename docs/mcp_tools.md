# AeroMaint MCP server

The MCP server is a JSON-RPC 2.0 boundary over AeroMaint's versioned public API. It supports MCP
protocol `2025-03-26` over authenticated HTTP `POST /mcp` and newline-delimited stdio. It never
imports repositories or accesses storage tables.

## Running the transports

For stdio, provide a public API base URL and the authenticated caller context:

```sh
AEROMAINT_API_URL=http://127.0.0.1:8000 \
AEROMAINT_MCP_USER_ID=local-user \
AEROMAINT_MCP_TOKEN=... \
AEROMAINT_MCP_PERMISSIONS=session:read,annotation:read \
uv run python -m services.mcp_server.transport
```

An ASGI host can serve `create_app(McpDispatcher(HttpPublicApiClient(api_url)))`. HTTP requests must
carry `Authorization: Bearer ...`, `X-User-ID`, and the gateway-derived `X-Permissions` header. The
same bearer token is forwarded to every public API call; mutation attribution and authorization are
therefore performed by the API using the original principal. `X-Trace-ID` is forwarded when present,
or the server creates one.

## Tools and resources

| Capability   | Tools                                          | Resource template                               |
| ------------ | ---------------------------------------------- | ----------------------------------------------- |
| Sessions     | `sessions.list`, `sessions.get`                | `aeromaint://sessions/{session_id}`             |
| Streams      | `streams.list`                                 | `aeromaint://sessions/{session_id}/streams`     |
| Model tracks | `model_tracks.get`, `predictions.get`          | `aeromaint://sessions/{session_id}/model-track` |
| Retrieval    | `documents.search`, `seek_events.lookup`       | —                                               |
| Annotations  | `annotations.list`, `annotations.create_draft` | `aeromaint://sessions/{session_id}/annotations` |
| Exports      | `exports.get`, `exports.create`                | `aeromaint://exports/{export_id}`               |

Inputs are Pydantic-generated JSON schemas with unknown fields prohibited. IDs are restricted to
safe opaque identifiers, nanosecond values are bounded 64-bit non-negative integers, intervals must
be ordered, page/search sizes are capped, and export stream IDs must be valid and unique. Query
parameters and path components are encoded rather than interpolated unsafely.

Calls default to a five-second end-to-end timeout and a 64,000-byte encoded output limit. Stable safe
errors include `invalid_arguments`, `unknown_tool`, `unauthenticated`, `permission_denied`,
`not_found`, `conflict`, `timeout`, `output_too_large`, `upstream_error`, and
`upstream_unavailable`. Upstream bodies and exception details are never returned. Structured start
and finish logs contain the trace ID, tool name, caller ID, and output size, but no token or payload.

The dispatcher accepts a failure-injection callback for deterministic timeout and upstream-failure
tests. Contract tests also exercise an initialize/list/call/resource golden scenario.

## Safety boundary

There is deliberately no tool for recommendation approval, annotation review, export cancellation,
or permission elevation. In particular, possessing `recommendation:approve` does not add an MCP
approval method. Approval remains an authenticated engineer action in the product review workflow.
