import { parseManifest } from "@aeromaint/contracts";
import type { ViewerDataSource } from "./sdk.js";

const BASE_NS = 9_007_199_254_740_993n;
const manifest = parseManifest({
  schema_version: "1.0.0",
  session_id: "synthetic-stereo",
  display_name: "Playable two-camera browser fixture",
  start_ns: BASE_NS.toString(),
  end_ns: (BASE_NS + 10_000_000_000n).toString(),
  session_clock_id: "session",
  clocks: [
    {
      id: "session",
      source_epoch_ns: "0",
      session_epoch_ns: "0",
      rate_numerator: 1,
      rate_denominator: 1
    }
  ],
  artifacts: [
    {
      id: "left-media",
      media_type: "video/webm; codecs=vp8",
      logical_key: "fixture/left.webm",
      size_bytes: 1,
      sha256: "1".repeat(64)
    },
    {
      id: "right-media",
      media_type: "video/webm; codecs=vp8",
      logical_key: "fixture/right.webm",
      size_bytes: 1,
      sha256: "2".repeat(64)
    }
  ],
  calibrations: [],
  streams: [
    {
      id: "camera-left",
      kind: "video",
      clock_id: "session",
      start_ns: BASE_NS.toString(),
      end_ns: (BASE_NS + 10_000_000_000n).toString(),
      sample_count: 300,
      schema_ref: "video/webm; codecs=vp8",
      artifact_ids: ["left-media"],
      calibration_ids: [],
      gaps: [
        {
          start_ns: (BASE_NS + 4_000_000_000n).toString(),
          end_ns: (BASE_NS + 5_000_000_000n).toString(),
          reason: "missing"
        }
      ]
    },
    {
      id: "camera-right",
      kind: "video",
      clock_id: "session",
      start_ns: BASE_NS.toString(),
      end_ns: (BASE_NS + 10_000_000_000n).toString(),
      sample_count: 300,
      schema_ref: "video/webm; codecs=vp8",
      artifact_ids: ["right-media"],
      calibration_ids: [],
      gaps: []
    }
  ],
  provenance: {
    source_type: "synthetic",
    source_uri: "fixture://browser-stereo",
    source_sha256: "a".repeat(64),
    adapter: "browser-fixture",
    adapter_version: "1"
  }
});

export function createSyntheticViewerDataSource(): ViewerDataSource {
  return {
    listSessions: () =>
      Promise.resolve([
        { id: manifest.sessionId, manifest, processingStatus: "ready" as const }
      ]),
    getSessionManifest: () => Promise.resolve(manifest),
    mediaSources: (_sessionId, stream) => [
      {
        src: `fixture://${stream.id}`,
        type: "video/webm; codecs=vp8",
        synthetic: {
          label: stream.id === "camera-left" ? "LEFT" : "RIGHT",
          hue: stream.id === "camera-left" ? 164 : 32
        }
      }
    ],
    loadVectorSamples: () => Promise.resolve([])
  };
}
