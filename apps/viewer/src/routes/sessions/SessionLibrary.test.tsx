import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { parseManifest } from "@aeromaint/contracts";
import { SessionLibrary } from "./SessionLibrary.js";

const manifest = parseManifest({
  schema_version: "1.0.0",
  session_id: "stereo",
  display_name: "Stereo run",
  start_ns: "0",
  end_ns: "2000000000",
  session_clock_id: "clock",
  clocks: [
    {
      id: "clock",
      source_epoch_ns: "0",
      session_epoch_ns: "0",
      rate_numerator: 1,
      rate_denominator: 1
    }
  ],
  artifacts: [],
  calibrations: [],
  streams: [],
  provenance: {
    source_type: "synthetic",
    source_uri: "fixture://stereo",
    source_sha256: "a".repeat(64),
    adapter: "fixture",
    adapter_version: "1"
  }
});

describe("SessionLibrary", () => {
  it("renders the required session metadata and processing state", () => {
    const html = renderToStaticMarkup(
      <SessionLibrary
        sessions={[{ id: "stereo", manifest, processingStatus: "ready" }]}
        onOpen={() => undefined}
      />
    );
    for (const expected of [
      "Stereo run",
      "synthetic",
      "2.00 s",
      "0",
      "1.0.0",
      "ready"
    ])
      expect(html).toContain(expected);
  });

  it("renders an explicit empty state", () => {
    expect(
      renderToStaticMarkup(
        <SessionLibrary sessions={[]} onOpen={() => undefined} />
      )
    ).toContain("No capture sessions");
  });
});
