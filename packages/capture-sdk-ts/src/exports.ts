import type { TimestampNs } from "@aeromaint/contracts";

export type ExportStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "expired";

export interface ExportRequest {
  readonly sessionId: string;
  /** Inclusive canonical session timestamp. */
  readonly startNs: TimestampNs;
  /** Exclusive canonical session timestamp. */
  readonly endNs: TimestampNs;
  readonly streamIds?: readonly string[];
  readonly sensorFormat?: "arrow" | "json";
  readonly includeAnnotations?: boolean;
}

export interface ExportJob {
  readonly id: string;
  readonly sessionId: string;
  readonly startNs: TimestampNs;
  readonly endNs: TimestampNs;
  readonly windowSemantics: "[start_ns,end_ns)";
  readonly streamIds: readonly string[];
  readonly sensorFormat: "arrow" | "json";
  readonly status: ExportStatus;
  readonly progress: number;
  readonly statusUrl: string;
  readonly manifestUrl?: string;
  readonly manifest?: Readonly<Record<string, unknown>>;
  readonly error?: Readonly<Record<string, unknown>>;
  readonly expiresAt: string;
}

function object(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new TypeError("Export response must be an object");
  return value as Record<string, unknown>;
}

export function exportBody(value: ExportRequest): Record<string, unknown> {
  if (value.endNs <= value.startNs)
    throw new RangeError("endNs must be greater than startNs; window is half-open");
  return {
    session_id: value.sessionId,
    start_ns: value.startNs.toString(),
    end_ns: value.endNs.toString(),
    stream_ids: value.streamIds ?? [],
    sensor_format: value.sensorFormat ?? "arrow",
    include_annotations: value.includeAnnotations ?? true
  };
}

export function parseExport(value: unknown): ExportJob {
  const item = object(value);
  const manifest =
    item.manifest === null || item.manifest === undefined
      ? undefined
      : object(item.manifest);
  const error =
    item.error === null || item.error === undefined
      ? undefined
      : object(item.error);
  const manifestUrl =
    typeof item.manifest_url === "string" ? item.manifest_url : undefined;
  return {
    id: String(item.id),
    sessionId: String(item.session_id),
    startNs: BigInt(String(item.start_ns)),
    endNs: BigInt(String(item.end_ns)),
    windowSemantics: "[start_ns,end_ns)",
    streamIds: Array.isArray(item.stream_ids)
      ? item.stream_ids.map(String)
      : [],
    sensorFormat: item.sensor_format === "json" ? "json" : "arrow",
    status: String(item.status) as ExportStatus,
    progress: Number(item.progress),
    statusUrl: String(item.status_url),
    ...(manifestUrl === undefined ? {} : { manifestUrl }),
    ...(manifest === undefined ? {} : { manifest }),
    ...(error === undefined ? {} : { error }),
    expiresAt: String(item.expires_at)
  };
}
