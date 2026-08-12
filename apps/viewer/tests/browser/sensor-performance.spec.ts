import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

test("large virtualized tracks remain responsive and memory bounded", async ({
  page,
  browserName
}) => {
  test.skip(
    browserName !== "chromium",
    "Chromium exposes the measured heap extension"
  );
  test.setTimeout(60_000);
  await page.goto("/sessions?fixture=1&sensorSamples=100000");
  await page
    .getByRole("button", { name: /Playable two-camera browser fixture/ })
    .click();
  await expect(page.locator('[data-virtualized-track="true"]')).toHaveCount(3, {
    timeout: 20_000
  });
  const baseline = await page.evaluate(() => {
    const memory = performance as Performance & {
      memory?: { usedJSHeapSize: number };
    };
    window.__AEROMAINT_LONG_TASKS__ = [];
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries())
        window.__AEROMAINT_LONG_TASKS__?.push(entry.duration);
    }).observe({ type: "longtask", buffered: false });
    return memory.memory?.usedJSHeapSize ?? 0;
  });
  for (let index = 0; index < 12; index += 1) {
    await page
      .locator('[data-virtualized-track="true"]')
      .nth(index % 2)
      .scrollIntoViewIfNeeded();
    await page.waitForTimeout(100);
  }
  const measured = await page.evaluate(() => {
    const memory = performance as Performance & {
      memory?: { usedJSHeapSize: number };
    };
    return {
      heapBytes: memory.memory?.usedJSHeapSize ?? 0,
      longTasksMs: window.__AEROMAINT_LONG_TASKS__ ?? []
    };
  });
  const report = {
    recordedAt: new Date().toISOString(),
    browser: await page.evaluate(() => navigator.userAgent),
    dataset: { tracks: 2, samplesPerTrack: 100_000, totalSamples: 200_000 },
    virtualization: "CSS content-visibility auto",
    baselineHeapBytes: baseline,
    finalHeapBytes: measured.heapBytes,
    heapGrowthBytes: Math.max(0, measured.heapBytes - baseline),
    longTaskCount: measured.longTasksMs.length,
    maxLongTaskMs: Math.max(0, ...measured.longTasksMs),
    budgets: { heapGrowthBytes: 64 * 1024 * 1024, maxLongTaskMs: 200 }
  };
  expect(report.heapGrowthBytes).toBeLessThanOrEqual(
    report.budgets.heapGrowthBytes
  );
  expect(report.maxLongTaskMs).toBeLessThanOrEqual(
    report.budgets.maxLongTaskMs
  );
  const reportPath = path.resolve(
    process.cwd(),
    "../../tests/browser-performance/reports/sensor-rendering.json"
  );
  await mkdir(path.dirname(reportPath), { recursive: true });
  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
});

declare global {
  interface Window {
    __AEROMAINT_LONG_TASKS__?: number[];
  }
}
