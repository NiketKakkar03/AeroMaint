import { describe, expect, it, vi } from "vitest";
import {
  BoundedFrameQueue,
  DecodeGeneration,
  selectDecoderCapability
} from "../src/index.js";

interface TestFrame {
  readonly timestampUs: number;
  close(): void;
}

const frame = (timestampUs: number): TestFrame => ({
  timestampUs,
  close: vi.fn()
});

describe("bounded decode resources", () => {
  it("orders frames and closes evicted and stale resources", () => {
    const queue = new BoundedFrameQueue<TestFrame>(2);
    const late = frame(30);
    const early = frame(10);
    const middle = frame(20);
    queue.push(late);
    queue.push(early);
    queue.push(middle);
    expect(early.close).toHaveBeenCalledOnce();
    expect(queue.takeAtOrBefore(25)).toBe(middle);
    queue.clear();
    expect(late.close).toHaveBeenCalledOnce();
  });

  it("invalidates stale seek work", () => {
    const generation = new DecodeGeneration();
    const stale = generation.begin();
    const current = generation.begin();
    expect(generation.isCurrent(stale)).toBe(false);
    expect(generation.isCurrent(current)).toBe(true);
  });

  it("keeps an explicit HTML fallback", async () => {
    await expect(selectDecoderCapability("avc1", null)).resolves.toEqual({
      mode: "html-media",
      reason: "WebCodecs is unavailable"
    });
  });
});
