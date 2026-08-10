# Backend threat model

## Scope and trust boundaries

This model covers the HTTP data API, its callers, authentication material, future service and
repository implementations, and append-only audit persistence. Imported aircraft data is untrusted
content. The API process, configured signing secret, and repository implementations are trusted only
within their documented interfaces. TLS termination and production identity-token issuance are
deployment responsibilities; the bundled HS256 issuer is development-only.

## Protected assets and invariants

- Session evidence is disclosed only with `session:read`.
- Annotation, analysis, approval, and administration actions require their named permissions.
- High-risk recommendation approval is limited to engineers and administrators.
- Every authorization decision is appended to the configured audit sink before a protected handler
  runs. Audit write failure fails the request closed.
- Mutations require an idempotency key. A key is scoped to the presented identity credential and can
  replay only the same method, path, query, and body.
- Authentication and request failures use stable RFC 7807 problem codes without parser internals.

## Threats and controls

| Threat | Control | Residual risk / production requirement |
| --- | --- | --- |
| Forged or downgraded JWT | HS256 signature verification and fixed algorithm, issuer, audience, expiry, not-before, subject, and role validation | Replace development issuer with managed asymmetric OIDC validation and key rotation |
| Privilege escalation | Closed role enum and explicit role-to-permission mapping; handlers name required permission | Review mapping changes as security-sensitive code |
| Cross-user replay or duplicate mutation | Credential-scoped idempotency records, request fingerprint comparison, and serialized first execution | Use a durable transactional store shared by all API replicas |
| Brute force or resource exhaustion | Per-principal rate-limiter protocol and bounded in-memory implementation | Enforce IP/edge limits before authentication and use a distributed limiter |
| Audit deletion or mutation | Append-only sink protocol exposes no update/delete operation | Use durable write-once storage, access controls, retention, integrity signing, and monitoring |
| Browser injection and framing | Restrictive CSP, no-sniff, deny framing, no-referrer, and no-store headers | Media routes may require a separately reviewed CSP and caching policy |
| Error-based information disclosure | Stable problem documents and generic token failures | Scrub structured application logs and protect observability access |
| Stolen signing secret or bearer token | Production refuses the known development secret; tokens require expiry | Store secrets in a manager, use short-lived tokens, TLS, rotation, and revocation strategy |

## Interface requirements

Production adapters must preserve the `Authenticator`, `RateLimiter`, `IdempotencyStore`, and
`AuditSink` contracts. Durable idempotency must atomically reserve a scoped key and commit its response.
Durable audit must append before the protected state transition and must never offer mutation methods.
Repository transactions implementing high-risk changes should write domain state and its audit event
atomically; the request-level authorization audit remains an independent enforcement record.
