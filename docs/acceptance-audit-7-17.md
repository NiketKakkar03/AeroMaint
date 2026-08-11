# Issues 7–17 acceptance audit

Audit date: 2026-08-10. Baseline: `4d38f8f` plus the changes on
`codex/issues-7-17-acceptance`.

This audit distinguishes implemented code from acceptance evidence. An issue is ready to close only
when every stated criterion and validation item has direct evidence.

| Issue                             | Status                      | Evidence                                                                                                                                                                           | Remaining acceptance work                                                                                                                                                    |
| --------------------------------- | --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #7 PostgreSQL persistence         | Verified                    | Four PostgreSQL integration tests pass against PostgreSQL 16: upgrade/downgrade, manifest/artifact persistence, concurrent import idempotency, append-only audit.                  | None found.                                                                                                                                                                  |
| #8 versioned APIs                 | Verified                    | API contract, boundary, pagination, typed error, ETag, frame-at, and range tests pass in the 70-test Python suite.                                                                 | None found.                                                                                                                                                                  |
| #9 Arrow/range transport          | Verified                    | Arrow round-trip and bounded-window memory tests plus nine HTTP range tests pass.                                                                                                  | None found.                                                                                                                                                                  |
| #10 TypeScript SDK/CLI            | Partially verified          | Eleven SDK tests and the live API/viewer path pass. SDK version policy and reference CLI exist.                                                                                    | Clean packed-consumer harness was attempted but could not complete after the sandbox blocked registry/cache access; re-run `pnpm test:sdk-pack` in normal CI before closing. |
| #11 backend security              | Verified                    | Fifteen authentication/authorization/idempotency/audit tests pass; threat model is present.                                                                                        | None found.                                                                                                                                                                  |
| #12 playback state machine        | Verified                    | Sixteen playback/decoder tests pass, covering deterministic transitions, gap/buffer behavior, nanosecond arithmetic, seek generations, bounded frame queues, and resource cleanup. | None found.                                                                                                                                                                  |
| #13 synchronized stereo surface   | Verified                    | Playwright verifies a playable two-camera fixture, authoritative playhead, deep-linked timestamp persistence, gap disclosure, and play/pause workflow.                             | None found.                                                                                                                                                                  |
| #14 sensor timeline/accessibility | Verified                    | IMU and pose tracks, zoom/rate/loop controls, bounded prefetch, rapid-request cancellation, raw-data labels, keyboard controls, duplicate-ID audit, and gap screenshot pass.       | None found.                                                                                                                                                                  |
| #15 playback metrics              | Verified                    | Retained 20-minute Chromium report contains 240 resource samples, 23,262 observed presentations, warm-seek/drift/transfer/long-task/heap metrics, identity, and passing budgets.   | Real codec decode and queue-depth measurements are intentionally tracked by #16.                                                                                             |
| #16 WebCodecs path                | Open (implementation slice) | Added capability detection, generation cancellation, bounded timestamp-ordered frame queue, worker decode protocol, and HTML fallback labeling; tests pass.                        | Integrate a real demuxer and worker-backed presentation path, then run capability, seek-storm, memory, and fallback browser suites.                                          |
| #17 scalable sensor rendering     | Open (implementation slice) | Added worker protocol, typed-array transfer boundary, pixel-bounded min/max envelopes, deterministic LRU window cache, Canvas rendering, and a one-million-sample/800-pixel test.  | Parse Arrow IPC in the worker, connect visible/prefetch window fetching and cache telemetry, virtualize multiple tracks, and capture browser long-task/memory evidence.      |

## Executed validation

- `pnpm check`: formatting, ESLint, strict TypeScript, 53 TypeScript tests — pass.
- Python suite without PostgreSQL networking: 66 tests — pass.
- PostgreSQL integration suite: 4 tests — pass in the earlier unrestricted local run against the
  `pgvector/pgvector:pg16` Compose service.
- In-app browser against live API/viewer: session library, session navigation, URL timestamp deep
  link, keyboard Home seek, fallback state, Canvas plot, diagnostics, accessible names, and duplicate
  ID audit — pass.
- Million-sample timeline envelope test: one million input samples produce exactly 800 viewport
  buckets and complete in under one second on the audit machine.

## Environment blockers

The final combined PostgreSQL and live Node SDK repetitions were blocked by the active command
sandbox denying localhost TCP connections. The same PostgreSQL test file passed all four tests in an
earlier unrestricted run during this audit. The packed-consumer harness also encountered unavailable
registry/cache artifacts. These are recorded as unverified gates rather than product failures.
