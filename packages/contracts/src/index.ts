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
  "startNs" | "endNs" | "streams"
> {
  readonly startNs: string;
  readonly endNs: string;
  readonly streams: readonly (Omit<CaptureStream, "startNs" | "endNs"> & {
    readonly startNs: string;
    readonly endNs: string;
  })[];
}

export function timestampNs(value: string | bigint): TimestampNs {
  return typeof value === "bigint" ? value : BigInt(value);
}

export function parseManifest(
  manifest: CaptureSessionManifestJson
): CaptureSessionManifest {
  return {
    ...manifest,
    startNs: timestampNs(manifest.startNs),
    endNs: timestampNs(manifest.endNs),
    streams: manifest.streams.map((stream) => ({
      ...stream,
      startNs: timestampNs(stream.startNs),
      endNs: timestampNs(stream.endNs)
    }))
  };
}
