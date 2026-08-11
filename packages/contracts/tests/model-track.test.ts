import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { parseModelTrack } from "../src/model-track.js";

describe("model track contract", () => {
  it("parses the golden artifact without losing nanosecond precision", () => {
    const fixture: unknown = JSON.parse(
      readFileSync(
        new URL(
          "../../../tests/contract/health/model-track-v1.json",
          import.meta.url
        ),
        "utf8"
      )
    );
    const track = parseModelTrack(fixture);
    expect(track.points[0]?.timestampNs).toBe(9_007_199_254_740_993n);
    expect(track.versions).toEqual({
      model: "rul-linear-1",
      features: "health-core-1",
      data: "capture-v1",
      code: "health-service-1"
    });
    expect(track.points[0]?.status).toBe("insufficient_history");
  });
});
