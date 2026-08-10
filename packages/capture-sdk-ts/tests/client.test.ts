import { readFileSync } from "node:fs";

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CaptureAbortError,
  CaptureClient,
  type CaptureSdkError
} from "../src/index.js";
import type { CaptureHttpError, SessionSummary } from "../src/index.js";

const fixture: Record<string, unknown> = JSON.parse(
  readFileSync(
    new URL(
      "../../../tests/contract/fixtures/capture-manifest-v1.json",
      import.meta.url
    ),
    "utf8"
  )
) as Record<string, unknown>;

afterEach(() => vi.useRealTimers());

describe("CaptureClient", () => {
  it("fetches manifests and preserves timestamps beyond Number precision", async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(new Response(JSON.stringify(fixture)));
    const client = new CaptureClient({ baseUrl: "http://api.test/", fetch });

    const manifest = await client.getSessionManifest("fixture/session");

    expect(manifest.startNs).toBe(9_007_199_254_740_993n);
    expect(fetch.mock.calls[0]?.[0]).toBe(
      "http://api.test/v1/sessions/fixture%2Fsession/manifest"
    );
  });

  it("injects fresh auth and user headers on every request", async () => {
    const auth = vi.fn().mockResolvedValue({ authorization: "Bearer fresh" });
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(new Response("[]"));
    const client = new CaptureClient({
      baseUrl: "https://api.test",
      fetch,
      auth,
      headers: { "x-client": "test" }
    });

    await client.listSessions();

    const headers = new Headers(fetch.mock.calls[0]?.[1]?.headers);
    expect(headers.get("authorization")).toBe("Bearer fresh");
    expect(headers.get("x-client")).toBe("test");
    expect(auth).toHaveBeenCalledOnce();
  });

  it("normalizes predecessor pagination envelopes", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          sessions: [
            {
              session_id: "s1",
              start_ns: "9007199254740993",
              end_ns: "9007199254740994"
            }
          ],
          nextCursor: "next"
        })
      )
    );
    const page = await new CaptureClient({
      baseUrl: "https://api.test",
      fetch
    }).listSessions({ limit: 1 });

    expect(page).toEqual({
      items: [
        {
          id: "s1",
          startNs: 9_007_199_254_740_993n,
          endNs: 9_007_199_254_740_994n
        }
      ],
      nextCursor: "next"
    });
  });

  it("iterates lazily and enforces the caller's bound", async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [{ id: "one", start_ns: "1", end_ns: "2" }],
            next_cursor: "2"
          })
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [{ id: "two", start_ns: "2", end_ns: "3" }],
            next_cursor: "3"
          })
        )
      );
    const iterator = new CaptureClient({
      baseUrl: "https://api.test",
      fetch
    }).iterateSessions({ pageSize: 1, maxItems: 2 });

    expect(fetch).not.toHaveBeenCalled();
    expect(
      ((await iterator.next()).value as SessionSummary | undefined)?.id
    ).toBe("one");
    expect(fetch).toHaveBeenCalledOnce();
    expect(
      ((await iterator.next()).value as SessionSummary | undefined)?.id
    ).toBe("two");
    expect((await iterator.next()).done).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("returns Arrow sample bytes and bigint range metadata", async () => {
    const bytes = new Uint8Array([65, 82, 82, 79, 87]);
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(bytes, {
        headers: {
          "content-type": "application/vnd.apache.arrow.stream",
          "x-next-cursor": "c2"
        }
      })
    );
    const range = await new CaptureClient({
      baseUrl: "https://api.test",
      fetch
    }).getSampleRange("s", "imu", { startNs: 1n, endNs: 2n });

    expect(new Uint8Array(range.data as ArrayBuffer)).toEqual(bytes);
    expect(range.nextCursor).toBe("c2");
    expect(fetch.mock.calls[0]?.[0]).toContain("start_ns=1&end_ns=2");
  });

  it("normalizes nanosecond fields in JSON sample windows", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      Response.json({
        start_ns: "9007199254740993",
        end_ns: "9007199254740994",
        samples: [{ timestamp_ns: "9007199254740993", x: 1 }]
      })
    );
    const range = await new CaptureClient({
      baseUrl: "https://api.test",
      fetch
    }).getSampleRange("s", "imu", { startNs: 1n, endNs: 2n, format: "json" });

    expect(range.startNs).toBe(9_007_199_254_740_993n);
    expect(range.data).toEqual([
      { timestamp_ns: 9_007_199_254_740_993n, x: 1 }
    ]);
  });

  it("normalizes frame lookup and supports gaps", async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            frame_number: 7,
            presentation_ns: "9007199254740993",
            keyframe: true
          })
        )
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = new CaptureClient({ baseUrl: "https://api.test", fetch });

    await expect(
      client.lookupFrame("s", "camera", { timestampNs: 1n, mode: "nearest" })
    ).resolves.toMatchObject({
      frameNumber: 7,
      presentationNs: 9_007_199_254_740_993n
    });
    await expect(
      client.lookupFrame("s", "camera", { timestampNs: 2n })
    ).resolves.toBeUndefined();
  });

  it("retries retryable responses but not client failures", async () => {
    vi.useFakeTimers();
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(new Response("busy", { status: 503 }))
      .mockResolvedValueOnce(new Response("[]"));
    const request = new CaptureClient({
      baseUrl: "https://api.test",
      fetch,
      retry: { baseDelayMs: 1 }
    }).listSessions();
    await vi.runAllTimersAsync();
    await expect(request).resolves.toEqual({ items: [] });
    expect(fetch).toHaveBeenCalledTimes(2);

    fetch.mockReset().mockResolvedValue(new Response("bad", { status: 400 }));
    await expect(
      new CaptureClient({ baseUrl: "https://api.test", fetch }).listSessions()
    ).rejects.toMatchObject({
      retryable: false,
      status: 400
    } satisfies Partial<CaptureHttpError>);
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("maps AbortSignal cancellation to a non-retryable typed error", async () => {
    const controller = new AbortController();
    controller.abort("stop");
    const fetch = vi.fn<typeof globalThis.fetch>();
    await expect(
      new CaptureClient({ baseUrl: "https://api.test", fetch }).listSessions({
        signal: controller.signal
      })
    ).rejects.toBeInstanceOf(CaptureAbortError);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("reports unsupported and malformed manifests as typed errors", async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...fixture, schema_version: "2.0.0" }))
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...fixture, start_ns: 42 }))
      );
    const client = new CaptureClient({ baseUrl: "https://api.test", fetch });

    await expect(client.getSessionManifest("fixture")).rejects.toMatchObject({
      code: "unsupported_schema"
    } satisfies Partial<CaptureSdkError>);
    await expect(client.getSessionManifest("fixture")).rejects.toMatchObject({
      code: "invalid_manifest"
    } satisfies Partial<CaptureSdkError>);
  });
});
