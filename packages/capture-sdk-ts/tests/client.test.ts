import { describe, expect, it, vi } from "vitest";

import { CaptureClient } from "../src/index.js";
import type { CaptureSdkError } from "../src/index.js";

const fixture = {
  schema_version: "1.0.0",
  session_id: "fixture-session-001",
  display_name: "Fixture",
  start_ns: "9007199254740993",
  end_ns: "9007199254741000",
  streams: []
};

describe("CaptureClient", () => {
  it("fetches a manifest and preserves timestamps beyond Number precision", async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(
        new Response(JSON.stringify(fixture), { status: 200 })
      );
    const client = new CaptureClient({ baseUrl: "http://api.test/", fetch });

    const manifest = await client.getSessionManifest("fixture/session");

    expect(manifest.startNs).toBe(9_007_199_254_740_993n);
    expect(fetch).toHaveBeenCalledWith(
      "http://api.test/v1/sessions/fixture%2Fsession/manifest",
      { signal: null }
    );
  });

  it("reports unsupported schema versions as typed errors", async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(
        new Response(JSON.stringify({ ...fixture, schema_version: "2.0.0" }))
      );
    const client = new CaptureClient({ baseUrl: "http://api.test", fetch });

    await expect(client.getSessionManifest("fixture")).rejects.toMatchObject({
      code: "unsupported_schema"
    } satisfies Partial<CaptureSdkError>);
  });

  it("rejects malformed manifests before exposing them to callers", async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(
        new Response(JSON.stringify({ ...fixture, start_ns: 42 }))
      );
    const client = new CaptureClient({ baseUrl: "http://api.test", fetch });

    await expect(client.getSessionManifest("fixture")).rejects.toMatchObject({
      code: "invalid_manifest"
    } satisfies Partial<CaptureSdkError>);
  });
});
