# TypeScript capture SDK reference and versioning

`@aeromaint/capture-sdk` is the supported boundary between TypeScript consumers and capture storage.
It exposes session, stream, manifest, sample-window, and frame domain contracts; storage paths and
persistence records are intentionally absent.

## API reference

`new CaptureClient({ baseUrl, fetch?, auth?, headers?, retry? })` creates a client. `auth` accepts a
bearer token, a header map, or an async header callback so short-lived credentials can be refreshed
per request. Retry defaults are three attempts with capped exponential backoff. Only transport
failures, HTTP 408, 429, and 5xx responses retry. Aborts, authentication failures, validation errors,
and other 4xx responses do not retry.

- `listSessions(options?)` returns one cursor page. `iterateSessions({ pageSize?, maxItems?, signal? })`
  lazily requests pages and stops at `maxItems` (default 1,000).
- `getSessionManifest(id, signal?)` and compatibility alias `getManifest(id, options?)` validate the
  manifest schema and return nanosecond fields as `bigint`.
- `listStreams(id, options?)` and `iterateStreams(id, options?)` provide normalized stream summaries.
- `getSampleRange(sessionId, streamId, request)` requests a bounded `[startNs, endNs]` window and
  returns Arrow bytes or JSON data without exposing an artifact location.
- `lookupFrame(sessionId, streamId, request)` performs deterministic `at_or_before` or `nearest`
  lookup and returns `undefined` for an HTTP 204 gap.

All network methods accept an `AbortSignal`. Failures are instances of `CaptureSdkError`; specific
transport, abort, and HTTP subclasses are exported. Inspect `code`, `status`, and `retryable` instead
of matching messages.

The client accepts the current `{ items, next_cursor }` envelopes and predecessor bare arrays or
`sessions`/`streams`/`data` envelopes. Camel-case response aliases are accepted only at this boundary;
returned SDK objects use camel case consistently.

## Compatibility and migration policy

The package follows semantic versioning. Removing or changing a public method, type, error code, or
accepted value requires a major version. Additive optional fields and methods require a minor version;
compatible fixes require a patch. The SDK version, `/v1` HTTP version, and manifest schema version are
independent.

Unknown additive wire fields are ignored. Unsupported manifest schema versions fail explicitly with
`unsupported_schema`. Before a major release, deprecated members remain for at least one minor release
and the release notes provide old/new examples. Consumers should upgrade one major version at a time,
resolve deprecations, run contract tests, and only then adopt a newer HTTP or manifest version.

| SDK | HTTP API | Manifest schema |
| --- | -------- | --------------- |
| 1.x | `/v1`    | `1.0.0`         |
