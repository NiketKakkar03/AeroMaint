# Viewer media benchmarks

The benchmark report schema is `aeromaint.viewer-benchmark/v1`. A run identifies its browser and version, hardware, dataset and dataset checksum/version, run ID, start time, measurement duration, and resource sampling interval. Reports are JSON-serializable and contain both raw resource observations and derived metrics.

## Stable definitions

- **Time to first frame:** elapsed monotonic time from viewer initialization to the first presented decoded frame.
- **Cold seek:** the first seek after loading a session. **Warm seeks** are all subsequent completed seeks. Seek latency ends when the target frame is presented; p50 and p95 use nearest-rank percentiles.
- **Dropped frame:** a frame the playback scheduler intentionally skips because its presentation deadline passed. **Late frame:** a presented frame whose deadline passed. The dropped-frame rate is dropped frames divided by all presentation opportunities (presented plus dropped frames).
- **Clock drift:** absolute difference between the authoritative session clock and the presented frame timestamp, sampled once per presented frame. Reports retain p50, p95, and maximum absolute drift.
- **Buffering:** each continuous interval where playback wants data but the decoded queue cannot supply the due frame. Count and total duration are reported. Queue depth is the number of decoded, unpresented frames.
- **Memory:** `performance.memory.usedJSHeapSize` at the first, last, and peak resource sample where the browser exposes it. Unsupported observations are omitted rather than reported as zero. Growth is last minus first.
- **Resources:** cumulative transfer size from Resource Timing, and long-task count/duration from the Long Tasks API where supported. These are browser-side indicators, not whole-system CPU measurements.

## Harness and budgets

`tests/browser-performance/benchmark-config.json` declares the deterministic 20-minute window, five-second sampling, synthetic and EuRoC fixtures, and initial regression budgets. A Playwright scenario supplies playback actions and emits typed collector events; the harness owns collection and JSON reporting, independent of rendered diagnostics or CSS.

Initial budgets are warm-seek p95 ≤ 250 ms, dropped-frame rate ≤ 1%, absolute drift p95 ≤ 20 ms, and heap growth ≤ 64 MiB over 20 minutes. They are versioned inputs copied into every report, and may be overridden explicitly by a benchmark environment without changing metric definitions.

For repeatability, use a release viewer build, fixed browser channel/version, no devtools, a named hardware profile, and fixture checksums from `SHA256SUMS`. Run each dataset from a fresh browser context for cold measurements. Warm-seek and bounded-memory comparisons should use identical action sequences and sampling intervals.
