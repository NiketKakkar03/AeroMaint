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

# Viewer benchmark

Run the retained browser benchmark with:

```sh
pnpm --filter @aeromaint/viewer test:benchmark
```

The default run is 20 minutes with five-second resource samples and writes
`tests/browser-performance/reports/viewer-20min.json`. The report records the browser, host, CPU,
dataset/schema version, measurement window, warm-seek percentiles, stereo drift, dropped-frame rate,
transferred bytes, long tasks, and JavaScript heap growth. CI smoke runs may override
`AEROMAINT_BENCHMARK_DURATION_MS` and `AEROMAINT_BENCHMARK_REPORT`, but only the default-duration
report is accepted as the retained bounded-memory gate.

## Retained result — 2026-08-11

The committed [20-minute report](../tests/browser-performance/reports/viewer-20min.json) was recorded
with Headless Chromium 151.0.7922.34 on an Apple M1 Pro (8 logical cores) using the version 1.0.0
synthetic stereo/IMU/pose manifest. It contains 240 five-second resource samples and 23,262 observed
stereo presentation updates.

| Metric                          |           Result |        Budget |
| ------------------------------- | ---------------: | ------------: |
| Time to first frame             |        201.44 ms | informational |
| Warm seek p50 / p95             | 14.24 / 21.60 ms |  p95 ≤ 250 ms |
| Dropped-frame rate              |               0% |          ≤ 1% |
| Absolute stereo drift p95 / max |         0 / 0 ms |   p95 ≤ 20 ms |
| JavaScript heap growth          |          0 bytes |      ≤ 64 MiB |
| Transferred bytes               |           85,350 | informational |
| Long tasks                      |                0 | informational |

All declared budgets passed. This fixture measures the synchronized synthetic presentation path and
viewer resource bounds; it does not claim hardware video-decoder throughput. The separate #16
browser suite encodes VP8 frames, demuxes IVF in a worker, presents transferable `VideoFrame`s through
a bounded queue, and verifies seek-generation cleanup and the HTML fallback.

## Scalable sensor rendering

The committed [sensor rendering report](../tests/browser-performance/reports/sensor-rendering.json)
records two virtualized 100,000-sample tracks in Chromium. After the envelope workers settled,
repeated cross-track scrolling produced zero long tasks and zero measured heap growth against the
64 MiB / 200 ms budgets. This complements the deterministic one-million-sample, 800-pixel envelope
test; the browser fixture is smaller so fixture generation is not mistaken for renderer work.
