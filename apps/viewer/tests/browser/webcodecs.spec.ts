import { expect, test } from "@playwright/test";

test("worker demuxes and presents VP8 while seek generations stay bounded", async ({
  page,
  browserName
}) => {
  test.skip(browserName !== "chromium", "WebCodecs fixture targets Chromium");
  await page.addInitScript(() => {
    const NativeWorker = window.Worker;
    Object.defineProperty(window, "__AEROMAINT_WORKERS__", {
      value: { created: 0, active: 0 },
      configurable: true
    });
    window.Worker = class extends NativeWorker {
      activeForTest = true;
      constructor(url: URL | string, options?: WorkerOptions) {
        super(url, options);
        const counters = (
          window as unknown as {
            __AEROMAINT_WORKERS__: { created: number; active: number };
          }
        ).__AEROMAINT_WORKERS__;
        counters.created += 1;
        counters.active += 1;
      }
      override terminate() {
        if (this.activeForTest) {
          const counters = (
            window as unknown as {
              __AEROMAINT_WORKERS__: { created: number; active: number };
            }
          ).__AEROMAINT_WORKERS__;
          counters.active -= 1;
          this.activeForTest = false;
        }
        super.terminate();
      }
    };
    const original = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const url = String(input);
      if (!url.endsWith(".ivf")) return original(input, init);
      const chunks: {
        data: Uint8Array;
        timestamp: number;
        type: EncodedVideoChunkType;
      }[] = [];
      const encoder = new VideoEncoder({
        output(chunk) {
          const data = new Uint8Array(chunk.byteLength);
          chunk.copyTo(data);
          chunks.push({ data, timestamp: chunk.timestamp, type: chunk.type });
        },
        error(error) {
          throw error;
        }
      });
      encoder.configure({
        codec: "vp8",
        width: 32,
        height: 16,
        bitrate: 100_000,
        framerate: 10
      });
      for (let index = 0; index < 20; index += 1) {
        const canvas = new OffscreenCanvas(32, 16);
        const context = canvas.getContext("2d")!;
        context.fillStyle = index % 2 ? "#19c37d" : "#ff6b35";
        context.fillRect(0, 0, 32, 16);
        const frame = new VideoFrame(canvas, { timestamp: index * 100_000 });
        encoder.encode(frame, { keyFrame: index === 0 });
        frame.close();
      }
      await encoder.flush();
      encoder.close();
      const length =
        32 +
        chunks.reduce((total, chunk) => total + 12 + chunk.data.byteLength, 0);
      const bytes = new Uint8Array(length);
      const view = new DataView(bytes.buffer);
      bytes.set([68, 75, 73, 70], 0);
      view.setUint16(6, 32, true);
      bytes.set([86, 80, 56, 48], 8);
      view.setUint16(12, 32, true);
      view.setUint16(14, 16, true);
      view.setUint32(16, 10, true);
      view.setUint32(20, 1, true);
      view.setUint32(24, chunks.length, true);
      let offset = 32;
      for (const chunk of chunks) {
        view.setUint32(offset, chunk.data.byteLength, true);
        const tick = BigInt(Math.round(chunk.timestamp / 100_000));
        view.setUint32(offset + 4, Number(tick & 0xffffffffn), true);
        view.setUint32(offset + 8, Number(tick >> 32n), true);
        bytes.set(chunk.data, offset + 12);
        offset += 12 + chunk.data.byteLength;
      }
      return new Response(bytes, {
        headers: { "content-type": "video/x-ivf" }
      });
    };
  });
  await page.goto("/sessions?fixture=webcodecs");
  await page
    .getByRole("button", { name: /Playable two-camera browser fixture/ })
    .click();
  await expect(page.getByText("WebCodecs worker · IVF demux")).toHaveCount(2);
  await expect(page.getByLabel("WebCodecs decoded media")).toHaveCount(2);
  const timeline = page.getByRole("slider", {
    name: "Session timeline",
    exact: true
  });
  for (const value of [100, 1700, 300, 1900, 800, 1200])
    await timeline.fill(String(value));
  await expect(page.locator("[role=alert]")).toHaveCount(0);
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as unknown as { __AEROMAINT_WORKERS__: { active: number } })
            .__AEROMAINT_WORKERS__.active
      )
    )
    .toBe(2);
});

test("labels the supported HTML fallback when WebCodecs is unavailable", async ({
  page
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(globalThis, "VideoDecoder", {
      value: undefined,
      configurable: true
    });
  });
  await page.goto("/sessions?fixture=1");
  await page
    .getByRole("button", { name: /Playable two-camera browser fixture/ })
    .click();
  await expect(page.getByText("HTML media fallback")).toHaveCount(2);
});
