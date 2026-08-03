import { describe, expect, it } from "vitest";

import {
  CAPTURE_MANIFEST_SCHEMA_VERSION,
  parseManifest
} from "../src/index.js";

describe("parseManifest", () => {
  it("preserves nanosecond precision with bigint", () => {
    const manifest = parseManifest({
      schemaVersion: CAPTURE_MANIFEST_SCHEMA_VERSION,
      sessionId: "fixture-01",
      displayName: "Fixture",
      startNs: "9007199254740993",
      endNs: "9007199254741000",
      streams: []
    });

    expect(manifest.startNs).toBe(9_007_199_254_740_993n);
  });
});
