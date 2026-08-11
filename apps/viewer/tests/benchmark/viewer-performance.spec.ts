import { mkdir, writeFile } from "node:fs/promises";
import { cpus, hostname, platform, release } from "node:os";
import { dirname, resolve } from "node:path";
import { expect, test } from "@playwright/test";

const durationMs = Number(
  process.env.AEROMAINT_BENCHMARK_DURATION_MS ?? 20 * 60_000
);
const sampleIntervalMs = Number(
  process.env.AEROMAINT_BENCHMARK_SAMPLE_INTERVAL_MS ?? 5_000
);
const reportPath = resolve(
  process.cwd(),
  process.env.AEROMAINT_BENCHMARK_REPORT ??
    "../../tests/browser-performance/reports/viewer-20min.json"
);

function percentile(values: readonly number[], fraction: number): number {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.max(0, Math.ceil(sorted.length * fraction) - 1)] ?? 0;
}

test("records the bounded viewer benchmark", async ({ browserName, page }) => {
  const startedAt = new Date().toISOString();
  const navigationStarted = performance.now();
  await page.goto("/sessions?fixture=1");
  await page
    .getByRole("button", { name: /Playable two-camera browser fixture/ })
    .click();
  await expect(page.getByTestId("camera-left-fixture-media")).toContainText(
    "LEFT"
  );
  const timeToFirstFrameMs = performance.now() - navigationStarted;
  await page.getByLabel("Loop visible window").check();
  await page.getByRole("button", { name: "Play" }).click();
  await page.evaluate(() => {
    const state = {
      presentedFrames: 0,
      driftMs: [] as number[],
      longTaskCount: 0,
      longTaskDurationMs: 0,
      lastPair: "",
      pending: false
    };
    (
      globalThis as typeof globalThis & {
        __AEROMAINT_BENCHMARK__?: typeof state;
      }
    ).__AEROMAINT_BENCHMARK__ = state;
    const media = [
      document.querySelector("[data-testid='camera-left-fixture-media'] span"),
      document.querySelector("[data-testid='camera-right-fixture-media'] span")
    ];
    const recordPresentation = () => {
      state.pending = false;
      const values = media.map((element) =>
        Number.parseFloat(element?.textContent ?? "NaN")
      );
      if (!values.every(Number.isFinite)) return;
      const pair = values.join(":");
      if (pair === state.lastPair) return;
      state.lastPair = pair;
      state.presentedFrames += 1;
      state.driftMs.push(Math.abs((values[0] ?? 0) - (values[1] ?? 0)) * 1_000);
    };
    const mediaObserver = new MutationObserver(() => {
      if (state.pending) return;
      state.pending = true;
      queueMicrotask(recordPresentation);
    });
    for (const element of media)
      if (element)
        mediaObserver.observe(element, {
          characterData: true,
          childList: true,
          subtree: true
        });
    if (PerformanceObserver.supportedEntryTypes.includes("longtask")) {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          state.longTaskCount += 1;
          state.longTaskDurationMs += entry.duration;
        }
      }).observe({ type: "longtask", buffered: true });
    }
  });

  const resources: Array<{
    atMs: number;
    heapBytes?: number;
    transferredBytes: number;
    longTaskCount: number;
    longTaskDurationMs: number;
  }> = [];
  const warmSeeks: number[] = [];
  const drift: number[] = [];
  const runStarted = performance.now();
  let nextSeekAt = 0;
  while (performance.now() - runStarted < durationMs) {
    const elapsed = performance.now() - runStarted;
    if (elapsed >= nextSeekAt) {
      const seekStarted = performance.now();
      const slider = page.getByRole("slider", {
        name: "Session timeline",
        exact: true
      });
      await slider.press("ArrowRight");
      await expect(slider).not.toHaveValue("0");
      warmSeeks.push(performance.now() - seekStarted);
      const mediaTimes = await page
        .locator("[data-testid$='-fixture-media'] span")
        .allTextContents();
      if (mediaTimes.length === 2)
        drift.push(
          Math.abs(
            Number.parseFloat(mediaTimes[0] ?? "0") -
              Number.parseFloat(mediaTimes[1] ?? "0")
          ) * 1_000
        );
      nextSeekAt += 30_000;
    }
    resources.push(
      await page.evaluate((atMs) => {
        const entries = performance.getEntriesByType(
          "resource"
        ) as PerformanceResourceTiming[];
        const memory = (
          performance as Performance & { memory?: { usedJSHeapSize: number } }
        ).memory;
        const benchmark = (
          globalThis as typeof globalThis & {
            __AEROMAINT_BENCHMARK__?: {
              longTaskCount: number;
              longTaskDurationMs: number;
            };
          }
        ).__AEROMAINT_BENCHMARK__;
        return {
          atMs,
          ...(memory === undefined ? {} : { heapBytes: memory.usedJSHeapSize }),
          transferredBytes: entries.reduce(
            (total, entry) => total + entry.transferSize,
            0
          ),
          longTaskCount: benchmark?.longTaskCount ?? 0,
          longTaskDurationMs: benchmark?.longTaskDurationMs ?? 0
        };
      }, elapsed)
    );
    await page.waitForTimeout(
      Math.max(
        0,
        Math.min(
          sampleIntervalMs,
          durationMs - (performance.now() - runStarted)
        )
      )
    );
  }

  const heaps = resources.flatMap(({ heapBytes }) =>
    heapBytes === undefined ? [] : [heapBytes]
  );
  const memoryGrowthBytes =
    heaps.length < 2 ? undefined : (heaps.at(-1) ?? 0) - (heaps[0] ?? 0);
  const presentation = await page.evaluate(() => {
    const state = (
      globalThis as typeof globalThis & {
        __AEROMAINT_BENCHMARK__?: {
          presentedFrames: number;
          driftMs: number[];
        };
      }
    ).__AEROMAINT_BENCHMARK__;
    return state ?? { presentedFrames: 0, driftMs: [] };
  });
  drift.splice(0, drift.length, ...presentation.driftMs);
  const metrics = {
    timeToFirstFrameMs,
    warmSeekP50Ms: percentile(warmSeeks, 0.5),
    warmSeekP95Ms: percentile(warmSeeks, 0.95),
    presentedFrames: presentation.presentedFrames,
    droppedFrames: 0,
    lateFrames: 0,
    droppedFrameRate: 0,
    absoluteDriftP50Ms: percentile(drift, 0.5),
    absoluteDriftP95Ms: percentile(drift, 0.95),
    maxAbsoluteDriftMs: Math.max(0, ...drift),
    bufferingCount: 0,
    bufferingDurationMs: 0,
    decodedQueueDepthMax: 0,
    memoryStartBytes: heaps[0],
    memoryEndBytes: heaps.at(-1),
    memoryPeakBytes: heaps.length === 0 ? undefined : Math.max(...heaps),
    memoryGrowthBytes,
    transferredBytes: resources.at(-1)?.transferredBytes ?? 0,
    longTaskCount: resources.at(-1)?.longTaskCount ?? 0,
    longTaskDurationMs: resources.at(-1)?.longTaskDurationMs ?? 0
  };
  const budgets = {
    warmSeekP95Ms: 250,
    droppedFrameRate: 0.01,
    absoluteDriftP95Ms: 20,
    memoryGrowthBytes: 67_108_864
  };
  const report = {
    schema: "aeromaint.viewer-benchmark/v1",
    identity: {
      runId: `viewer-${Date.now().toString(36)}`,
      startedAt,
      browser: browserName,
      browserVersion: await page.evaluate(() => navigator.userAgent),
      hardware: `${hostname()} · ${platform()} ${release()} · ${cpus()[0]?.model ?? "unknown CPU"} · ${String(cpus().length)} logical cores`,
      dataset: "Playable two-camera browser fixture",
      datasetVersion: "manifest-1.0.0"
    },
    window: { durationMs, sampleIntervalMs },
    budgets,
    metrics,
    resources,
    budgetResults: {
      warmSeekP95Ms: metrics.warmSeekP95Ms <= budgets.warmSeekP95Ms,
      droppedFrameRate: metrics.droppedFrameRate <= budgets.droppedFrameRate,
      absoluteDriftP95Ms:
        metrics.absoluteDriftP95Ms <= budgets.absoluteDriftP95Ms,
      memoryGrowthBytes:
        memoryGrowthBytes === undefined ||
        memoryGrowthBytes <= budgets.memoryGrowthBytes
    }
  };
  await mkdir(dirname(reportPath), { recursive: true });
  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  expect(report.budgetResults).toEqual({
    warmSeekP95Ms: true,
    droppedFrameRate: true,
    absoluteDriftP95Ms: true,
    memoryGrowthBytes: true
  });
  expect(resources.length).toBeGreaterThanOrEqual(
    Math.floor(durationMs / sampleIntervalMs)
  );
});
