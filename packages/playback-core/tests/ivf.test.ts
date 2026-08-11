import { describe, expect, it } from "vitest";
import { demuxIvf } from "../src/index.js";

function fixture(): ArrayBuffer {
  const bytes = new Uint8Array(32 + 12 + 3);
  const view = new DataView(bytes.buffer);
  bytes.set([68, 75, 73, 70], 0);
  view.setUint16(6, 32, true);
  bytes.set([86, 80, 56, 48], 8);
  view.setUint16(12, 16, true);
  view.setUint16(14, 8, true);
  view.setUint32(16, 30, true);
  view.setUint32(20, 1, true);
  view.setUint32(24, 1, true);
  view.setUint32(32, 3, true);
  bytes.set([0, 1, 2], 44);
  return bytes.buffer;
}

describe("IVF demuxing", () => {
  it("returns decoder configuration and timestamped encoded frames", () => {
    const video = demuxIvf(fixture());
    expect(video.config).toMatchObject({
      codec: "vp8",
      codedWidth: 16,
      codedHeight: 8
    });
    expect(video.frames).toHaveLength(1);
    expect(video.frames[0]).toMatchObject({ timestampUs: 0, key: true });
  });

  it("rejects malformed and truncated containers", () => {
    expect(() => demuxIvf(new ArrayBuffer(8))).toThrow("Invalid IVF header");
    const buffer = fixture().slice(0, -1);
    expect(() => demuxIvf(buffer)).toThrow("Truncated IVF frame");
  });
});
