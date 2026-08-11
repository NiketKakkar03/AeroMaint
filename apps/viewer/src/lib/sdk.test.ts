import { describe, expect, it, vi } from "vitest";
import { createViewerDataSource } from "./sdk.js";

describe("viewer SDK adapter", () => {
  it("forwards its bearer token and maps Arrow samples with bigint timestamps", async () => {
    const encoded =
      "/////xABAAAQAAAAAAAKAAwABgAFAAgACgAAAAABBAAMAAAACAAIAAAABAAIAAAABAAAAAQAAACgAAAAXAAAADAAAAAEAAAAgP///wAAAQMQAAAAFAAAAAQAAAAAAAAAAgAAAGF6AACu////AAACAKj///8AAAEDEAAAABQAAAAEAAAAAAAAAAIAAABheQAA1v///wAAAgDQ////AAABAxAAAAAcAAAABAAAAAAAAAACAAAAYXgAAAAABgAIAAYABgAAAAAAAgAQABQACAAGAAcADAAAABAAEAAAAAAAAQIQAAAAKAAAAAQAAAAAAAAADAAAAHRpbWVzdGFtcF9ucwAAAAAIAAwACAAHAAgAAAAAAAABQAAAAP////8YAQAAFAAAAAAAAAAMABYABgAFAAgADAAMAAAAAAMEABgAAABIAAAAAAAAAAAACgAYAAwABAAIAAoAAACcAAAAEAAAAAIAAAAAAAAAAAAAAAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAABAAAAAAAAAAAQAAAAAAAAAYAAAAAAAAABAAAAAAAAAAKAAAAAAAAAAAAAAAAAAAACgAAAAAAAAAEAAAAAAAAAA4AAAAAAAAAAAAAAAAAAAAOAAAAAAAAAAQAAAAAAAAAAAAAAAEAAAAAgAAAAAAAAAAAAAAAAAAAAIAAAAAAAAAAQAAAAAAAAACAAAAAAAAAAAAAAAAAAAAAgAAAAAAAAAAAAAAAAAAAAEAAAAAACAAAgAAAAAAIAABAAAAAAAAAAAAAAAAAPg/AAAAAAAAAAAAAAAAAAAEQAAAAAAAAAxAAAAAAAAAEkAAAAAAAAAWQP////8AAAAA";
    const bytes = Uint8Array.from(atob(encoded), (character) =>
      character.charCodeAt(0)
    );
    const fetchImplementation = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(new Response(bytes));
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
    ).resolves.toEqual([
      { timeNs: 9007199254740993n, x: 1.5, y: 2.5, z: 4.5 },
      { timeNs: 9007199254740994n, x: Number.NaN, y: 3.5, z: 5.5 }
    ]);

    const request = fetchImplementation.mock.calls[0]?.[1];
    expect(new Headers(request?.headers).get("authorization")).toBe(
      "Bearer viewer-token"
    );
    expect(fetchImplementation.mock.calls[0]?.[0]).toContain("/samples/arrow?");
    await source.loadVectorSamples(
      "fixture-session-001",
      "imu-main",
      9007199254740993n,
      9007199259740993n
    );
    expect(fetchImplementation).toHaveBeenCalledTimes(1);
  });
});
