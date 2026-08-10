# ADR 0007: Shared nanosecond playback state machine

- Status: Accepted
- Date: 2026-08-10

## Context

The viewer coordinates media and sensor streams with different clocks, gaps, buffering behavior, and asynchronous seek completion. Letting a media element own time would make synchronization framework-specific and allow callbacks from old seeks to overwrite newer user intent. JavaScript numbers also cannot represent capture-scale nanosecond timestamps exactly.

## Decision

`@aeromaint/playback-core` owns an immutable, framework-independent state machine. Its public playhead, ranges, buffer boundaries, drift, and seek targets are `bigint` nanoseconds. Elapsed monotonic time is multiplied by a fixed-point representation of the playback rate, keeping timestamp arithmetic integral at API boundaries.

The explicit states are `idle`, `loading`, `ready`, `playing`, `paused`, `seeking`, `ended`, and `error`. Unsupported events are identity transitions. Configuration errors throw immediately. A clock-driven coordinator is a convenience around the pure reducer; neither layer imports React or browser media APIs.

The selected master stream alone determines playback gaps and buffering. Entering a master gap advances to its exclusive end. A known master buffer that does not cover the next playhead stalls playback without accumulating wall-clock time; extending that buffer resumes from a new clock anchor. Missing buffer information is treated as unknown/permissive. Non-master stream availability is observable but cannot stall the authoritative playhead.

End-of-stream clamps exactly to the source end. A loop treats its end as the wrap boundary and carries overshoot with modulo arithmetic. Rate changes first materialize elapsed time at the old rate and then establish a new anchor.

Every seek request increments a monotonically increasing generation. Only completion or failure matching the current generation can change state. A seek target is clamped to the active source/loop bounds and moved past a master-stream gap deterministically.

## Consequences

Adapters translate state into media, decoder, and rendering commands and report buffers, drift, and seek completions back with generations. UI frameworks subscribe to state rather than owning playback semantics. The reducer, fake monotonic clock, table tests, and seeded race tests provide reproducible behavior without timers or DOM globals.
