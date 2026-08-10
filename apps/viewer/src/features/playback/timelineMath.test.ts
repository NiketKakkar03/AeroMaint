import type { StreamGap } from "@aeromaint/contracts";
import { describe, expect, it } from "vitest";
import {
  clampTime,
  formatSessionTime,
  gapAt,
  ratioToTime,
  stepTime,
  timeToRatio
} from "./timelineMath";

const range = { startNs: 1_000_000_000n, endNs: 11_000_000_000n };

describe("timeline math", () => {
  it("maps selections between nanoseconds and a normalized timeline", () => {
    expect(timeToRatio(3_500_000_000n, range)).toBe(0.25);
    expect(ratioToTime(0.25, range)).toBe(3_500_000_000n);
    expect(ratioToTime(2, range)).toBe(range.endNs);
  });

  it("clamps seeks and keyboard steps to session bounds", () => {
    expect(clampTime(0n, range)).toBe(range.startNs);
    expect(stepTime(range.startNs, -33_333_333n, range)).toBe(range.startNs);
    expect(stepTime(range.endNs, 33_333_333n, range)).toBe(range.endNs);
  });

  it("treats gap ends as exclusive and exposes their reason", () => {
    const gaps: readonly StreamGap[] = [
      { startNs: 3n, endNs: 5n, reason: "clock_discontinuity" }
    ];
    expect(gapAt(3n, gaps)?.reason).toBe("clock_discontinuity");
    expect(gapAt(5n, gaps)).toBeUndefined();
  });

  it("formats session-relative time without losing millisecond precision", () => {
    expect(formatSessionTime(62_234_000_000n, 0n)).toBe("01:02.234");
  });
});
