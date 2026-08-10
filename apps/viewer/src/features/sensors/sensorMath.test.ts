import type { StreamGap } from "@aeromaint/contracts";
import { describe, expect, it } from "vitest";
import {
  closestSample,
  sampleSegments,
  valueExtent,
  type VectorSample
} from "./sensorMath";

const sample = (timeNs: bigint, x = Number(timeNs)): VectorSample => ({
  timeNs,
  x,
  y: x + 1,
  z: x + 2
});

describe("sensor plot math", () => {
  it("splits lines across declared gaps and removes samples inside them", () => {
    const gaps: readonly StreamGap[] = [
      { startNs: 2n, endNs: 4n, reason: "missing" }
    ];
    const segments = sampleSegments(
      [sample(1n), sample(2n), sample(3n), sample(4n), sample(5n)],
      gaps
    );
    expect(
      segments.map((segment) => segment.map(({ timeNs }) => timeNs))
    ).toEqual([[1n], [4n, 5n]]);
  });

  it("selects the nearest sensor sample for a playback time", () => {
    expect(
      closestSample([sample(1n), sample(5n), sample(9n)], 7n)?.timeNs
    ).toBe(5n);
    expect(closestSample([], 7n)).toBeUndefined();
  });

  it("adds a usable extent for a constant-valued series", () => {
    expect(valueExtent([{ timeNs: 0n, x: 2, y: 2, z: 2 }])).toEqual([1, 3]);
  });
});
