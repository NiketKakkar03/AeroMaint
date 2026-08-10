import { CaptureClient } from "@aeromaint/capture-sdk";
import type {
  CaptureSessionManifest,
  CaptureStream
} from "@aeromaint/contracts";

export interface SessionSummary {
  readonly id: string;
  readonly manifest?: CaptureSessionManifest;
  readonly processingStatus: "ready" | "processing" | "failed";
}

export interface MediaSource {
  readonly src: string;
  readonly type?: string;
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
  fetchImplementation: typeof globalThis.fetch = globalThis.fetch
): ViewerDataSource {
  const normalizedBase = baseUrl.replace(/\/$/, "");
  const client = new CaptureClient({
    baseUrl: normalizedBase,
    fetch: fetchImplementation
  });
  return {
    async listSessions(signal) {
      const response = await fetchImplementation(
        `${normalizedBase}/v1/sessions`,
        { signal: signal ?? null }
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
    }
  };
}
