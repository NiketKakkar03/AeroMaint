import { describe, expect, it } from "vitest";
import {
  SeekCoordinator,
  timestampFromUrl,
  timestampInGap,
  urlWithTimestamp
} from "./timeline.js";

const range = {
  startNs: 9_007_199_254_740_993n,
  endNs: 9_007_199_454_740_993n
};

describe("authoritative timeline", () => {
  it("round-trips precise timestamps through a shareable URL", () => {
    const timestamp = 9_007_199_374_740_993n;
    const url = urlWithTimestamp(
      new URL("https://viewer.test/sessions/sync?panel=media"),
      timestamp
    );
    expect(url).toBe(`/sessions/sync?panel=media&t=${timestamp.toString()}`);
    expect(
      timestampFromUrl(new URL(url, "https://viewer.test").search, range)
    ).toBe(timestamp);
  });

  it("clamps URL timestamps and exposes half-open stream gaps", () => {
    expect(timestampFromUrl("?t=999999999999999999", range)).toBe(range.endNs);
    const gap = {
      startNs: range.startNs + 10n,
      endNs: range.startNs + 20n,
      reason: "missing" as const
    };
    expect(timestampInGap(gap.startNs, [gap])).toBe(gap);
    expect(timestampInGap(gap.endNs, [gap])).toBeUndefined();
  });

  it("rejects stale seek completions", () => {
    const coordinator = new SeekCoordinator();
    const stale = coordinator.begin();
    const current = coordinator.begin();
    expect(coordinator.isCurrent(stale)).toBe(false);
    expect(coordinator.isCurrent(current)).toBe(true);
  });
});
