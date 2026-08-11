import { describe, expect, it } from "vitest";
import { WindowCache, envelopeForViewport } from "../src/index.js";

describe("viewport timeline rendering", () => {
  it("bounds million-sample work products by viewport width", () => {
    const samples = Array.from({ length: 1_000_000 }, (_, index) => ({
      timeNs: BigInt(index),
      value: Math.sin(index / 100)
    }));
    const envelope = envelopeForViewport(samples, 0n, 999_999n, 800);
    expect(envelope).toHaveLength(800);
    expect(envelope.reduce((sum, item) => sum + item.count, 0)).toBe(1_000_000);
  });

  it("evicts least-recently-used windows deterministically", () => {
    const cache = new WindowCache<number>(2);
    cache.set("a", 1);
    cache.set("b", 2);
    expect(cache.get("a")).toBe(1);
    expect(cache.set("c", 3)).toBe("b");
  });
});
