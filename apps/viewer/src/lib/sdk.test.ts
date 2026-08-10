import { describe, expect, it, vi } from "vitest";
import { createViewerDataSource } from "./sdk.js";

describe("viewer SDK adapter", () => {
  it("forwards its bearer token and maps JSON samples for sensor plots", async () => {
    const fetchImplementation = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(
        Response.json({
          items: [
            {
              timestamp_ns: "9007199254740993",
              values: { ax: 1, ay: 2, az: 3 }
            }
          ],
          range: {
            start_ns: "9007199254740993",
            end_ns: "9007199259740993",
            end_exclusive: true
          }
        })
      );
    const source = createViewerDataSource(
      "https://api.example.test",
      fetchImplementation,
      "viewer-token"
    );

    await expect(
      source.loadVectorSamples(
        "fixture-session-001",
        "imu-main",
        9007199254740993n,
        9007199259740993n
      )
    ).resolves.toEqual([{ timeNs: 9007199254740993n, x: 1, y: 2, z: 3 }]);

    const request = fetchImplementation.mock.calls[0]?.[1];
    expect(new Headers(request?.headers).get("authorization")).toBe(
      "Bearer viewer-token"
    );
  });
});
