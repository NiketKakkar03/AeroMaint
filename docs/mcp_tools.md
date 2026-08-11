# MCP tool boundary

The Phase 7 MCP dispatcher exposes five bounded tools: session lookup, deterministic prediction
lookup, cited document search, annotation draft creation, and synchronized export creation. Handlers
call the public versioned API client; they never query storage tables.

Arguments use strict schemas with no unknown fields. Each call carries the caller's bearer token and
returns a trace identifier. Calls default to a five-second timeout and 64 KB response budget. Errors
are mapped to stable `invalid_arguments`, `unknown_tool`, `timeout`, and `output_too_large` codes.

There is deliberately no recommendation-approval tool. Approval remains an authenticated engineer
action in the product review workflow and cannot be delegated through MCP.
