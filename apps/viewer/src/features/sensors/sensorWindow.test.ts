import { describe, expect, it } from "vitest";
import { sensorWindow } from "./sensorWindow.js";

describe("sensorWindow", () => {
  it("bounds visible and prefetch ranges to the session", () => {
    expect(sensorWindow(0n, 1_000n, 500n, 4)).toEqual({
      visibleStartNs: 375n,
      visibleEndNs: 625n,
      requestStartNs: 325n,
      requestEndNs: 675n
    });
    expect(sensorWindow(0n, 1_000n, 0n, 4).requestStartNs).toBe(0n);
    expect(sensorWindow(0n, 1_000n, 1_000n, 4).requestEndNs).toBe(1_000n);
  });

  it("uses stable half-window buckets to avoid refetching every tick", () => {
    const first = sensorWindow(0n, 1_000n, 510n, 4);
    const second = sensorWindow(0n, 1_000n, 560n, 4);
    expect(second).toEqual(first);
  });
});
