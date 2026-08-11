# @aeromaint/capture-sdk

The public TypeScript client for AeroMaint capture sessions. It converts nanosecond timestamps to
`bigint`, validates manifests, supports bearer or callback-based authentication, cancellation,
bounded retries, lazy cursor iteration, Arrow/JSON sample windows, and frame lookup.

Versioned annotation methods include `listAnnotations`, `createAnnotation`,
`updateAnnotation`, `reviewAnnotation`, and `annotationHistory`. Mutations
require an idempotency key. Updates and reviews send the expected version in
the body and `If-Match`; stale writes raise a typed `conflict` error.

```ts
import { CaptureClient } from "@aeromaint/capture-sdk";

const client = new CaptureClient({
  baseUrl: "http://localhost:8000",
  auth: () => ({ authorization: `Bearer ${process.env.AEROMAINT_TOKEN ?? ""}` })
});

for await (const session of client.iterateSessions({ maxItems: 100 })) {
  console.log(session.id, session.startNs);
}
```

See [`docs/sdk_versioning.md`](../../docs/sdk_versioning.md) for the API reference and compatibility
policy.
