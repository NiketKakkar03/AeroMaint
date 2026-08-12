# AeroMaint threat model

## Scope and classification

This model covers local ingestion, artifact storage, HTTP/API and SDK clients, browser viewer,
research ML, document retrieval, MCP tools, development authentication, and release artifacts.
Imported data/documents and all client input are untrusted. **The system is non-operational and has no
authority to make or approve maintenance, airworthiness, dispatch, or return-to-service decisions.**

## Assets and trust boundaries

- Source evidence, provenance, timestamps, calibrations, annotations, exports, and model artifacts.
- Credentials, authorization/audit records, idempotency state, and local database/files.
- Approved document corpus, citations, model/retrieval versions, reports, and release checksums.
- Boundaries: source → adapter; browser/SDK → API; API → storage; documents → retrieval; MCP client →
  bounded tools; generated output → qualified human; Git commit → release archive.

## Threats, controls, and residual risk

| Threat                               | Implemented control                                                                                       | Residual risk / required production control                                     |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Malformed/path-traversing source     | Schema checks, safe archive paths, bounded supported formats, checksums                                   | Parser fuzzing, sandboxed decoding, malware scanning                            |
| Timestamp/provenance tampering       | Canonical signed-width ns contracts and retained source metadata                                          | Cryptographic provenance and trusted acquisition chain                          |
| Forged/downgraded JWT                | Fixed HS256 algorithm, issuer/audience/time/role validation; known dev secret rejected in production mode | Managed asymmetric OIDC, TLS, rotation/revocation                               |
| Privilege escalation                 | Closed roles and named permissions                                                                        | Independent policy review and least-privilege deployment identities             |
| Duplicate/cross-user mutation        | Credential-scoped idempotency and request fingerprints                                                    | Durable transactional shared store                                              |
| Audit loss/tampering                 | Append-only interface; protected request fails closed when audit append fails                             | WORM storage, signing, retention, monitoring, domain/audit atomicity            |
| Browser injection/framing            | CSP, no-sniff, deny framing, no-referrer/no-store defaults                                                | Separate reviewed media/caching policy and dependency scanning                  |
| Resource exhaustion                  | Request/output/tool budgets, timeouts, bounded queues/ranges, rate-limiter interface                      | Edge limits, quotas, distributed limiter, load testing                          |
| Poisoned documents/citation spoofing | Explicit approved manifest, local paths, canonical HTTPS URLs, citation-preserving results                | Publisher signature/checksum policy, corpus review, prompt-injection evaluation |
| Unsafe model extrapolation           | Missing/non-finite/history/training-range abstention; model/data/feature versions                         | Representative OOD/drift validation; calibrated monitoring and governance       |
| Agent/tool overreach                 | Strict tool schemas, call/response limits, public API boundary, no approval tool                          | Adversarial tool testing and human-factors evaluation                           |
| Secret leakage in demo/release       | `.env` ignored; demo avoids printing token; `git archive HEAD` from clean tree                            | Secret scanning, signed release, protected CI provenance                        |
| Supply-chain compromise              | Locked pnpm/uv dependencies and CI checks                                                                 | Dependency attestations, vulnerability policy, pinned actions by digest         |

## Abuse cases

The design must fail safely when an attacker uploads a decompression bomb, forges a source clock,
replays an annotation mutation, injects instructions into a retrieved document, asks MCP to approve a
recommendation, submits oversized ranges, or republishes a modified archive under a trusted name.
Current controls reject or bound several of these cases; those requiring production infrastructure
remain explicit residual risks, not completed gates.

## Security verification status

Authentication/authorization/idempotency behavior has automated tests in
[`apps/data-api/tests/test_security.py`](../apps/data-api/tests/test_security.py). Source adapter and
MCP contracts have deterministic tests. No external penetration test, formal safety assessment,
fuzzing campaign, SBOM attestation, or production incident exercise has been run for this release.
