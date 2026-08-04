export const CAPTURE_MANIFEST_SCHEMA_VERSION = "1.0.0" as const;

export type TimestampNs = bigint;

export interface TimeRange {
  readonly startNs: TimestampNs;
  readonly endNs: TimestampNs;
}

export type StreamKind = "video" | "imu" | "pose" | "event" | "telemetry";

export interface CaptureStream {
  readonly id: string;
  readonly kind: StreamKind;
  readonly clockId: string;
  readonly startNs: TimestampNs;
  readonly endNs: TimestampNs;
  readonly sampleCount: number;
}

export interface CaptureSessionManifest {
  readonly schemaVersion: typeof CAPTURE_MANIFEST_SCHEMA_VERSION;
  readonly sessionId: string;
  readonly displayName: string;
  readonly startNs: TimestampNs;
  readonly endNs: TimestampNs;
  readonly streams: readonly CaptureStream[];
}

export interface CaptureSessionManifestJson extends Omit<
  CaptureSessionManifest,
  | "schemaVersion"
  | "sessionId"
  | "displayName"
  | "startNs"
  | "endNs"
  | "streams"
> {
  readonly schema_version: typeof CAPTURE_MANIFEST_SCHEMA_VERSION;
  readonly session_id: string;
  readonly display_name: string;
  readonly start_ns: string;
  readonly end_ns: string;
  readonly streams: readonly (Omit<
    CaptureStream,
    "clockId" | "startNs" | "endNs" | "sampleCount"
  > & {
    readonly clock_id: string;
    readonly start_ns: string;
    readonly end_ns: string;
    readonly sample_count: number;
  })[];
}

export function timestampNs(value: string | bigint): TimestampNs {
  return typeof value === "bigint" ? value : BigInt(value);
}

export function parseManifest(
  manifest: CaptureSessionManifestJson
): CaptureSessionManifest {
  return {
    schemaVersion: manifest.schema_version,
    sessionId: manifest.session_id,
    displayName: manifest.display_name,
    startNs: timestampNs(manifest.start_ns),
    endNs: timestampNs(manifest.end_ns),
    streams: manifest.streams.map((stream) => ({
      id: stream.id,
      kind: stream.kind,
      clockId: stream.clock_id,
      startNs: timestampNs(stream.start_ns),
      endNs: timestampNs(stream.end_ns),
      sampleCount: stream.sample_count
    }))
  };
}
