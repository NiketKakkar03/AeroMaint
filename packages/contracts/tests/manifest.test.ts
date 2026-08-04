import { describe, expect, it } from "vitest";

import {
  CAPTURE_MANIFEST_SCHEMA_VERSION,
  parseManifest
} from "../src/index.js";

describe("parseManifest", () => {
  it("preserves nanosecond precision with bigint", () => {
    const manifest = parseManifest({
      schema_version: CAPTURE_MANIFEST_SCHEMA_VERSION,
      session_id: "fixture-01",
      display_name: "Fixture",
      start_ns: "9007199254740993",
      end_ns: "9007199254741000",
      streams: []
    });

    expect(manifest.startNs).toBe(9_007_199_254_740_993n);
  });
});
