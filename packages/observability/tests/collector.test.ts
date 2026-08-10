import { describe, expect, it } from "vitest";
import { PlaybackMetricsCollector, REPORT_SCHEMA } from "../src/index.js";

const identity = {
  runId: "fixed",
  startedAt: "2026-08-10T00:00:00.000Z",
  browser: "Chromium",
  browserVersion: "1",
  hardware: "fixture",
  dataset: "synthetic-session",
  datasetVersion: "sha256:fixture"
};

describe("PlaybackMetricsCollector", () => {
  it("produces stable percentiles, rates, drift and budget results", () => {
    const collector = new PlaybackMetricsCollector(100);
    collector.record({ type: "first-frame", atMs: 145 });
    collector.record({ type: "seek", warm: false, latencyMs: 80 });
    for (const latencyMs of [10, 20, 30, 40, 50])
      collector.record({ type: "seek", warm: true, latencyMs });
    collector.record({ type: "frame", driftMs: -3 });
    collector.record({ type: "frame", driftMs: 7, late: true });
    collector.record({ type: "frame", driftMs: 0, dropped: true });
    collector.record({ type: "buffering", durationMs: 25 });
    collector.record({ type: "queue-depth", depth: 4 });
    collector.record({
      type: "resource",
      observation: {
        atMs: 0,
        heapBytes: 100,
        transferredBytes: 10,
        longTaskCount: 0,
        longTaskDurationMs: 0
      }
    });
    collector.record({
      type: "resource",
      observation: {
        atMs: 1000,
        heapBytes: 140,
        transferredBytes: 50,
        longTaskCount: 1,
        longTaskDurationMs: 60
      }
    });
    const report = collector.report(identity, 1000, 1000, {
      warmSeekP95Ms: 50,
      droppedFrameRate: 0.3,
      absoluteDriftP95Ms: 7,
      memoryGrowthBytes: 40
    });
    expect(report.schema).toBe(REPORT_SCHEMA);
    expect(report.metrics).toMatchObject({
      timeToFirstFrameMs: 45,
      coldSeekMs: 80,
      warmSeekP50Ms: 30,
      warmSeekP95Ms: 50,
      droppedFrameRate: 1 / 3,
      absoluteDriftP95Ms: 7,
      memoryGrowthBytes: 40,
      decodedQueueDepthMax: 4
    });
    expect(report.budgetResults).toEqual({
      warmSeekP95Ms: true,
      droppedFrameRate: false,
      absoluteDriftP95Ms: true,
      memoryGrowthBytes: true
    });
  });

  it("keeps a twenty-minute sample window bounded to the supplied interval", () => {
    const collector = new PlaybackMetricsCollector();
    for (let atMs = 0; atMs <= 20 * 60_000; atMs += 5_000)
      collector.record({
        type: "resource",
        observation: {
          atMs,
          heapBytes: 1_000 + atMs / 1000,
          transferredBytes: atMs,
          longTaskCount: 0,
          longTaskDurationMs: 0
        }
      });
    const report = collector.report(identity, 20 * 60_000, 5_000);
    expect(report.resources).toHaveLength(241);
    expect(report.metrics.memoryGrowthBytes).toBe(1200);
  });
});
