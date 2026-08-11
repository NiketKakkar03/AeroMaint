import { CaptureClient } from "@aeromaint/capture-sdk";
import type {
  Annotation,
  AnnotationDraft,
  AnnotationReview,
  AnnotationUpdate
} from "@aeromaint/capture-sdk";
import type {
  CaptureSessionManifest,
  CaptureStream
} from "@aeromaint/contracts";
import type { VectorSample } from "../features/sensors/sensorMath.js";
import { WindowCache } from "@aeromaint/timeline-renderer";
import type {
  ArrowWorkerRequest,
  ArrowWorkerResponse
} from "../workers/arrow.worker.js";
import { parseArrowVectorStream } from "../workers/arrow-ipc.js";

const defaultFetch: typeof globalThis.fetch = (input, init) =>
  globalThis.fetch(input, init);
const sensorCache = new WindowCache<readonly VectorSample[]>(8);
const sensorTelemetry = { hits: 0, misses: 0, evictions: 0 };

declare global {
  interface Window {
    __AEROMAINT_SENSOR_CACHE__?: {
      hits: number;
      misses: number;
      evictions: number;
    };
  }
}

function parseArrowInWorker(
  buffer: ArrayBuffer,
  signal?: AbortSignal
): Promise<readonly VectorSample[]> {
  if (typeof Worker === "undefined") {
    const columns = parseArrowVectorStream(buffer);
    return Promise.resolve(
      Array.from({ length: columns.timestampsNs.length }, (_, index) => ({
        timeNs: columns.timestampsNs[index] ?? 0n,
        x: columns.x[index] ?? Number.NaN,
        y: columns.y[index] ?? Number.NaN,
        z: columns.z[index] ?? Number.NaN
      }))
    );
  }
  return new Promise((resolve, reject) => {
    const worker = new Worker(
      new URL("../workers/arrow.worker.ts", import.meta.url),
      {
        type: "module"
      }
    );
    const id = crypto.randomUUID();
    const close = () => {
      worker.terminate();
    };
    const abort = () => {
      close();
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", abort, { once: true });
    worker.onmessage = (event: MessageEvent<ArrowWorkerResponse>) => {
      if (event.data.id !== id) return;
      signal?.removeEventListener("abort", abort);
      close();
      if (event.data.type === "error") {
        reject(new Error(event.data.message));
        return;
      }
      if (event.data.type !== "samples") return;
      const { timestampsNs, x, y, z } = event.data.columns;
      resolve(
        Array.from({ length: timestampsNs.length }, (_, index) => ({
          timeNs: timestampsNs[index] ?? 0n,
          x: x[index] ?? Number.NaN,
          y: y[index] ?? Number.NaN,
          z: z[index] ?? Number.NaN
        }))
      );
    };
    worker.onerror = () => {
      signal?.removeEventListener("abort", abort);
      close();
      reject(new Error("Arrow worker failed"));
    };
    worker.postMessage(
      { type: "arrow", id, buffer } satisfies ArrowWorkerRequest,
      [buffer]
    );
  });
}

export interface SessionSummary {
  readonly id: string;
  readonly manifest?: CaptureSessionManifest;
  readonly processingStatus: "ready" | "processing" | "failed";
}

export interface MediaSource {
  readonly src: string;
  readonly type?: string;
  readonly compatibility?: "unsupported";
  /** Deterministic browser-only media used by the public viewer smoke fixture. */
  readonly synthetic?: { readonly label: string; readonly hue: number };
}

export interface ViewerDataSource {
  listSessions(signal?: AbortSignal): Promise<readonly SessionSummary[]>;
  getSessionManifest(
    sessionId: string,
    signal?: AbortSignal
  ): Promise<CaptureSessionManifest>;
  mediaSources(
    sessionId: string,
    stream: CaptureStream,
    manifest: CaptureSessionManifest
  ): readonly MediaSource[];
  loadVectorSamples(
    sessionId: string,
    streamId: string,
    startNs: bigint,
    endNs: bigint,
    signal?: AbortSignal
  ): Promise<readonly VectorSample[]>;
  listAnnotations(
    sessionId: string,
    signal?: AbortSignal
  ): Promise<readonly Annotation[]>;
  createAnnotation(
    sessionId: string,
    draft: AnnotationDraft
  ): Promise<Annotation>;
  updateAnnotation(
    sessionId: string,
    id: string,
    update: AnnotationUpdate
  ): Promise<Annotation>;
  reviewAnnotation(
    sessionId: string,
    id: string,
    review: AnnotationReview
  ): Promise<Annotation>;
  annotationHistory(
    sessionId: string,
    id: string
  ): ReturnType<CaptureClient["annotationHistory"]>;
}

interface SessionListItem {
  readonly id?: string;
  readonly session_id?: string;
  readonly status?: string;
}

function itemsFromPayload(payload: unknown): readonly SessionListItem[] {
  if (Array.isArray(payload)) return payload as SessionListItem[];
  if (typeof payload !== "object" || payload === null) return [];
  const record = payload as Record<string, unknown>;
  const items = record.sessions ?? record.items;
  return Array.isArray(items) ? (items as SessionListItem[]) : [];
}

function processingStatus(
  value: string | undefined
): SessionSummary["processingStatus"] {
  if (value === "failed" || value === "error") return "failed";
  if (value === "processing" || value === "pending") return "processing";
  return "ready";
}

export function createViewerDataSource(
  baseUrl = "/api",
  fetchImplementation: typeof globalThis.fetch = defaultFetch,
  token?: string
): ViewerDataSource {
  const normalizedBase = baseUrl.replace(/\/$/, "");
  const client = new CaptureClient({
    baseUrl: normalizedBase,
    fetch: fetchImplementation,
    ...(token === undefined || token.length === 0 ? {} : { auth: token })
  });
  const authorizationHeaders =
    token === undefined || token.length === 0
      ? undefined
      : { Authorization: `Bearer ${token}` };
  return {
    async listSessions(signal) {
      const response = await fetchImplementation(
        `${normalizedBase}/v1/sessions`,
        {
          ...(authorizationHeaders === undefined
            ? {}
            : { headers: authorizationHeaders }),
          signal: signal ?? null
        }
      );
      if (!response.ok)
        throw new Error(`Session request failed (${String(response.status)})`);
      const items = itemsFromPayload(await response.json());
      return Promise.all(
        items.flatMap((item) => {
          const id = item.session_id ?? item.id;
          if (!id) return [];
          return [
            client.getSessionManifest(id, signal).then(
              (manifest): SessionSummary => ({
                id,
                manifest,
                processingStatus: processingStatus(item.status)
              }),
              (): SessionSummary => ({
                id,
                processingStatus: processingStatus(item.status)
              })
            )
          ];
        })
      );
    },
    getSessionManifest: (sessionId, signal) =>
      client.getSessionManifest(sessionId, signal),
    listAnnotations: (sessionId, signal) =>
      client.listAnnotations(sessionId, signal ? { signal } : {}),
    createAnnotation: (sessionId, draft) =>
      client.createAnnotation(sessionId, draft, {
        idempotencyKey: crypto.randomUUID()
      }),
    updateAnnotation: (sessionId, id, update) =>
      client.updateAnnotation(sessionId, id, update, {
        idempotencyKey: crypto.randomUUID()
      }),
    reviewAnnotation: (sessionId, id, review) =>
      client.reviewAnnotation(sessionId, id, review, {
        idempotencyKey: crypto.randomUUID()
      }),
    annotationHistory: (sessionId, id) =>
      client.annotationHistory(sessionId, id),
    mediaSources(sessionId, stream, manifest) {
      const artifact = manifest.artifacts.find((candidate) =>
        stream.artifactIds.includes(candidate.id)
      );
      const src = `${normalizedBase}/v1/sessions/${encodeURIComponent(sessionId)}/streams/${encodeURIComponent(stream.id)}/media`;
      return artifact?.mediaType.startsWith("video/")
        ? [{ src, type: artifact.mediaType }]
        : [{ src }];
    },
    async loadVectorSamples(sessionId, streamId, startNs, endNs, signal) {
      const key = `${sessionId}:${streamId}:${startNs.toString()}:${endNs.toString()}`;
      const telemetry =
        typeof window === "undefined"
          ? sensorTelemetry
          : (window.__AEROMAINT_SENSOR_CACHE__ ??= sensorTelemetry);
      const cached = sensorCache.get(key);
      if (cached) {
        telemetry.hits += 1;
        return cached;
      }
      telemetry.misses += 1;
      const query = new URLSearchParams({
        start_ns: startNs.toString(),
        end_ns: endNs.toString()
      });
      const response = await fetchImplementation(
        `${normalizedBase}/v1/sessions/${encodeURIComponent(sessionId)}/streams/${encodeURIComponent(streamId)}/samples/arrow?${query.toString()}`,
        {
          ...(authorizationHeaders === undefined
            ? {}
            : { headers: authorizationHeaders }),
          signal: signal ?? null
        }
      );
      if (!response.ok)
        throw new Error(`Sample request failed (${String(response.status)})`);
      const samples = await parseArrowInWorker(
        await response.arrayBuffer(),
        signal
      );
      if (sensorCache.set(key, samples) !== undefined) telemetry.evictions += 1;
      return samples;
    }
  };
}
