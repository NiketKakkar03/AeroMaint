import { CaptureClient } from "@aeromaint/capture-sdk";
import type {
  CaptureSessionManifest,
  CaptureStream
} from "@aeromaint/contracts";
import type { VectorSample } from "../features/sensors/sensorMath.js";

const defaultFetch: typeof globalThis.fetch = (input, init) =>
  globalThis.fetch(input, init);

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
      const range = await client.getSampleRange(sessionId, streamId, {
        startNs,
        endNs,
        format: "json",
        limit: 100,
        ...(signal === undefined ? {} : { signal })
      });
      if (!Array.isArray(range.data)) return [];
      return range.data.flatMap((candidate): VectorSample[] => {
        if (typeof candidate !== "object" || candidate === null) return [];
        const row = candidate as Record<string, unknown>;
        const values =
          typeof row.values === "object" && row.values !== null
            ? (row.values as Record<string, unknown>)
            : row;
        const timestamp = row.timestamp_ns ?? row.timestampNs;
        const x = values.x ?? values.ax ?? values.px;
        const y = values.y ?? values.ay ?? values.py;
        const z = values.z ?? values.az ?? values.pz;
        return typeof timestamp === "bigint" &&
          typeof x === "number" &&
          typeof y === "number" &&
          typeof z === "number"
          ? [{ timeNs: timestamp, x, y, z }]
          : [];
      });
    }
  };
}
