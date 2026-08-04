import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { ManifestValidationError, parseManifest } from "../src/index.js";

const fixture: unknown = JSON.parse(
  readFileSync(
    new URL(
      "../../../tests/contract/fixtures/capture-manifest-v1.json",
      import.meta.url
    ),
    "utf8"
  )
);

function cloneFixture(): Record<string, unknown> {
  return structuredClone(fixture) as Record<string, unknown>;
}

function firstStream(
  manifest: Record<string, unknown>
): Record<string, unknown> {
  const first = (manifest.streams as Record<string, unknown>[]).at(0);
  if (first === undefined) throw new Error("fixture must contain a stream");
  return first;
}

describe("parseManifest", () => {
  it("validates the shared golden fixture and preserves nanosecond precision", () => {
    const manifest = parseManifest(fixture);

    expect(manifest.startNs).toBe(9_007_199_254_740_993n);
    expect(manifest.clocks[1]?.rateNumerator).toBe(1_000_001);
    expect(manifest.streams[0]?.gaps[0]?.reason).toBe("missing");
    expect(manifest.provenance.adapterVersion).toBe("1.0.0");
  });

  it("rejects noncanonical, out-of-range, and reversed timestamps", () => {
    for (const invalid of ["01", "1.5", "9223372036854775808"]) {
      const candidate = cloneFixture();
      candidate.start_ns = invalid;
      expect(() => parseManifest(candidate), invalid).toThrow(
        ManifestValidationError
      );
    }

    const reversed = cloneFixture();
    reversed.start_ns = "9007199454740994";
    expect(() => parseManifest(reversed)).toThrow(/end_ns must be greater/);
  });

  it("rejects streams connected to an unknown clock", () => {
    const candidate = cloneFixture();
    firstStream(candidate).clock_id = "missing-clock";

    expect(() => parseManifest(candidate)).toThrow(/unknown clock/);
  });

  it("rejects overlapping gaps rather than hiding missing evidence", () => {
    const candidate = cloneFixture();
    const stream = firstStream(candidate);
    stream.gaps = [
      ...(stream.gaps as unknown[]),
      {
        start_ns: "9007199354740993",
        end_ns: "9007199394740993",
        reason: "corrupt"
      }
    ];

    expect(() => parseManifest(candidate)).toThrow(
      /ordered and non-overlapping/
    );
  });

  it("tolerates additive fields for backward-compatible schema evolution", () => {
    const candidate = cloneFixture();
    candidate.future_optional_metadata = { producer: "future-version" };

    expect(parseManifest(candidate).sessionId).toBe("fixture-session-001");
  });
});
