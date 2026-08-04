import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  frameAtOrBefore,
  mapToSessionTime,
  nearestFrame,
  parseManifest,
  timestampNs,
  type IndexedFrame
} from "../src/index.js";

const fixtureRoot = new URL(
  "../../../tests/media-fixtures/synthetic-session/",
  import.meta.url
);

function json(name: string): unknown {
  return JSON.parse(readFileSync(new URL(name, fixtureRoot), "utf8"));
}

interface Expectations {
  readonly base_ns: string;
  readonly clock_mappings: readonly {
    readonly clock_id: string;
    readonly source_ns: string;
    readonly expected_session_ns: string;
  }[];
  readonly frame_queries: readonly {
    readonly offset_ns: string;
    readonly at_or_before: number | null;
    readonly nearest: number | null;
  }[];
}

function frameIndex(name: string): readonly IndexedFrame[] {
  const value = json(name) as {
    readonly frames: readonly {
      readonly frame_number: number;
      readonly presentation_ns: string;
      readonly keyframe: boolean;
    }[];
  };
  return value.frames.map((frame) => ({
    frameNumber: frame.frame_number,
    presentationNs: timestampNs(frame.presentation_ns),
    keyframe: frame.keyframe
  }));
}

describe("deterministic synchronization fixture", () => {
  const manifest = parseManifest(json("manifest.json"));
  const expectations = json("expectations.json") as Expectations;

  it("maps offset and drifting source clocks with exact integer arithmetic", () => {
    for (const expectation of expectations.clock_mappings) {
      const clock = manifest.clocks.find(
        (candidate) => candidate.id === expectation.clock_id
      );
      if (clock === undefined)
        throw new Error(`missing fixture clock ${expectation.clock_id}`);

      expect(mapToSessionTime(timestampNs(expectation.source_ns), clock)).toBe(
        timestampNs(expectation.expected_session_ns)
      );
    }
  });

  it("selects at-or-before and nearest frames and refuses evidence inside gaps", () => {
    const frames = frameIndex("camera-left-index.json");
    const stream = manifest.streams.find(
      (candidate) => candidate.id === "camera-left"
    );
    if (stream === undefined)
      throw new Error("missing left camera fixture stream");
    const baseNs = timestampNs(expectations.base_ns);

    for (const query of expectations.frame_queries) {
      const requestedNs = baseNs + timestampNs(query.offset_ns);
      expect(
        frameAtOrBefore(frames, requestedNs, stream.gaps)?.frameNumber ?? null
      ).toBe(query.at_or_before);
      expect(
        nearestFrame(frames, requestedNs, stream.gaps)?.frameNumber ?? null
      ).toBe(query.nearest);
    }
  });

  it("uses the earlier frame as the deterministic nearest-frame tie break", () => {
    const frames = frameIndex("camera-left-index.json");
    const baseNs = timestampNs(expectations.base_ns);

    expect(nearestFrame(frames, baseNs + 25_000_000n)?.frameNumber).toBe(0);
  });
});
