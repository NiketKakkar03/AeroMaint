import { parseManifest } from "@aeromaint/contracts";
import type {
  Annotation,
  AnnotationDraft,
  ExportJob
} from "@aeromaint/capture-sdk";
import type { ViewerDataSource } from "./sdk.js";

const BASE_NS = 9_007_199_254_740_993n;
declare global {
  interface Window {
    __AEROMAINT_FIXTURE_REQUESTS__?: { started: number; aborted: number };
  }
}
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
    },
    {
      id: "imu-main",
      kind: "imu",
      clock_id: "session",
      start_ns: BASE_NS.toString(),
      end_ns: (BASE_NS + 10_000_000_000n).toString(),
      sample_count: 2_000,
      schema_ref: "aeromaint://schemas/imu/1.0.0",
      artifact_ids: [],
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
      id: "pose-main",
      kind: "pose",
      clock_id: "session",
      start_ns: BASE_NS.toString(),
      end_ns: (BASE_NS + 10_000_000_000n).toString(),
      sample_count: 1_000,
      schema_ref: "aeromaint://schemas/pose/1.0.0",
      artifact_ids: [],
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

export function createSyntheticViewerDataSource(
  workerMedia = false,
  sensorSampleCount = 64
): ViewerDataSource {
  let annotations: Annotation[] = [];
  let fixtureExport: ExportJob | undefined;
  const save = (draft: AnnotationDraft, current?: Annotation) => {
    const now = new Date().toISOString();
    const item: Annotation = {
      id: current?.id ?? crypto.randomUUID(),
      sessionId: manifest.sessionId,
      ...(draft.streamId === undefined ? {} : { streamId: draft.streamId }),
      startNs: draft.startNs,
      endNs: draft.endNs ?? draft.startNs,
      shape:
        (draft.endNs ?? draft.startNs) === draft.startNs ? "point" : "interval",
      kind: draft.kind,
      payload: draft.payload ?? {},
      version: (current?.version ?? 0) + 1,
      status: current?.status ?? "draft",
      actor: "fixture-analyst",
      provenance: draft.provenance ?? { source: "viewer-fixture" },
      createdAt: current?.createdAt ?? now,
      updatedAt: now
    };
    annotations = [...annotations.filter(({ id }) => id !== item.id), item];
    return item;
  };
  return {
    listSessions: () =>
      Promise.resolve([
        { id: manifest.sessionId, manifest, processingStatus: "ready" as const }
      ]),
    getSessionManifest: () => Promise.resolve(manifest),
    getModelTrack: () =>
      Promise.resolve({
        schemaVersion: "1.0.0" as const,
        artifactId: "prediction-fixture-v1",
        engineId: "ENG-FIXTURE",
        sessionId: manifest.sessionId,
        createdAt: "2026-08-11T00:00:00Z",
        versions: {
          model: "fixture-1",
          features: "fixture-1",
          data: "fixture-1",
          code: "fixture-1"
        },
        points: [
          {
            timestampNs: manifest.startNs,
            status: "insufficient_history" as const,
            rul: null,
            rulUnit: "cycles" as const,
            interval: null,
            horizon: 30,
            horizonUnit: "cycles" as const,
            anomalyScore: null,
            anomalySeverity: "none" as const,
            reason: "requires at least 3 observations",
            oodFeatures: [],
            attribution: []
          },
          {
            timestampNs: manifest.endNs,
            status: "ok" as const,
            rul: 142,
            rulUnit: "cycles" as const,
            interval: [125, 159] as const,
            horizon: 30,
            horizonUnit: "cycles" as const,
            anomalyScore: 1.2,
            anomalySeverity: "none" as const,
            oodFeatures: [],
            attribution: [
              { feature: "vibration", contribution: -1.4, unit: "cycles" }
            ]
          }
        ]
      }),
    listAnnotations: () => Promise.resolve(annotations),
    createAnnotation: (_sessionId, draft) => Promise.resolve(save(draft)),
    updateAnnotation: (_sessionId, id, update) => {
      const current = annotations.find((item) => item.id === id);
      if (current?.version !== update.expectedVersion)
        return Promise.reject(
          new Error("Annotation changed; reload before editing.")
        );
      return Promise.resolve(save(update, current));
    },
    reviewAnnotation: (_sessionId, id, review) => {
      const current = annotations.find((item) => item.id === id);
      if (current?.version !== review.expectedVersion)
        return Promise.reject(
          new Error("Annotation changed; reload before reviewing.")
        );
      const updated = {
        ...current,
        version: current.version + 1,
        status: review.decision,
        actor: "fixture-engineer",
        updatedAt: new Date().toISOString()
      };
      annotations = annotations.map((item) =>
        item.id === id ? updated : item
      );
      return Promise.resolve(updated);
    },
    annotationHistory: (_sessionId, id) =>
      Promise.resolve(
        annotations
          .filter((item) => item.id === id)
          .map((item) => ({
            id: item.version,
            occurredAt: item.updatedAt,
            actor: item.actor,
            action: `annotation.${item.status}`,
            payload: { version: item.version }
          }))
      ),
    createExport: (sessionId, startNs, endNs, sensorFormat) => {
      fixtureExport = {
        id: crypto.randomUUID(),
        sessionId,
        startNs,
        endNs,
        windowSemantics: "[start_ns,end_ns)",
        streamIds: manifest.streams.map(({ id }) => id),
        sensorFormat,
        status: "succeeded",
        progress: 1,
        statusUrl: "/fixture/export",
        manifestUrl: "/fixture/export/manifest.json",
        expiresAt: new Date(Date.now() + 86_400_000).toISOString()
      };
      return Promise.resolve(fixtureExport);
    },
    getExport: () =>
      fixtureExport
        ? Promise.resolve(fixtureExport)
        : Promise.reject(new Error("Export not found")),
    cancelExport: () => {
      if (!fixtureExport) return Promise.reject(new Error("Export not found"));
      fixtureExport = { ...fixtureExport, status: "cancelled", progress: 0 };
      return Promise.resolve(fixtureExport);
    },
    exportFileUrl: (path) => path,
    mediaSources: (_sessionId, stream) =>
      workerMedia
        ? [{ src: `/fixtures/${stream.id}.ivf`, type: "video/x-ivf" }]
        : [
            {
              src: `fixture://${stream.id}`,
              type: "video/webm; codecs=vp8",
              synthetic: {
                label: stream.id === "camera-left" ? "LEFT" : "RIGHT",
                hue: stream.id === "camera-left" ? 164 : 32
              }
            }
          ],
    loadVectorSamples: (_sessionId, streamId, startNs, endNs, signal) => {
      if (signal?.aborted)
        return Promise.reject(new DOMException("Aborted", "AbortError"));
      const count = sensorSampleCount;
      const duration = endNs - startNs;
      const fixtureRequests = (window.__AEROMAINT_FIXTURE_REQUESTS__ ??= {
        started: 0,
        aborted: 0
      });
      fixtureRequests.started += 1;
      return new Promise((resolve, reject) => {
        const onAbort = () => {
          window.clearTimeout(timer);
          fixtureRequests.aborted += 1;
          reject(new DOMException("Aborted", "AbortError"));
        };
        const timer = window.setTimeout(() => {
          signal?.removeEventListener("abort", onAbort);
          const samples = Array.from({ length: count }, (_, index) => {
            const ratio = index / (count - 1);
            const phase = ratio * Math.PI * 4;
            return {
              timeNs:
                startNs +
                BigInt(Math.round(Number(duration) * Math.min(1, ratio))),
              x: Math.sin(phase) * (streamId === "imu-main" ? 9.81 : 2),
              y: Math.cos(phase * 0.7) * (streamId === "imu-main" ? 4 : 1),
              z: Math.sin(phase * 0.3) * (streamId === "imu-main" ? 2 : 0.5)
            };
          });
          resolve(samples);
        }, 25);
        signal?.addEventListener("abort", onAbort, { once: true });
      });
    }
  };
}
