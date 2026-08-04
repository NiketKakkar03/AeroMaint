export const CAPTURE_MANIFEST_SCHEMA_VERSION = "1.0.0" as const;

const MIN_I64 = -(1n << 63n);
const MAX_I64 = (1n << 63n) - 1n;
const DECIMAL_INTEGER = /^-?(0|[1-9][0-9]*)$/;
const SHA256 = /^[a-f0-9]{64}$/;

export type TimestampNs = bigint;
export type StreamKind = "video" | "imu" | "pose" | "event" | "telemetry";

export interface TimeRange {
  readonly startNs: TimestampNs;
  readonly endNs: TimestampNs;
}

export interface ClockDefinition {
  readonly id: string;
  readonly sourceEpochNs: TimestampNs;
  readonly sessionEpochNs: TimestampNs;
  readonly rateNumerator: number;
  readonly rateDenominator: number;
}

export interface ArtifactDescriptor {
  readonly id: string;
  readonly mediaType: string;
  readonly logicalKey: string;
  readonly sizeBytes: number;
  readonly sha256: string;
}

export interface CalibrationReference {
  readonly id: string;
  readonly kind: string;
  readonly artifactId: string;
}

export interface StreamGap extends TimeRange {
  readonly reason: "missing" | "corrupt" | "clock_discontinuity";
}

export interface CaptureStream extends TimeRange {
  readonly id: string;
  readonly kind: StreamKind;
  readonly clockId: string;
  readonly sampleCount: number;
  readonly schemaRef: string;
  readonly artifactIds: readonly string[];
  readonly calibrationIds: readonly string[];
  readonly gaps: readonly StreamGap[];
}

export interface ManifestProvenance {
  readonly sourceType: string;
  readonly sourceUri: string;
  readonly sourceSha256: string;
  readonly adapter: string;
  readonly adapterVersion: string;
}

export interface CaptureSessionManifest extends TimeRange {
  readonly schemaVersion: typeof CAPTURE_MANIFEST_SCHEMA_VERSION;
  readonly sessionId: string;
  readonly displayName: string;
  readonly sessionClockId: string;
  readonly clocks: readonly ClockDefinition[];
  readonly artifacts: readonly ArtifactDescriptor[];
  readonly calibrations: readonly CalibrationReference[];
  readonly streams: readonly CaptureStream[];
  readonly provenance: ManifestProvenance;
}

export interface CaptureSessionManifestJson {
  readonly schema_version: string;
  readonly session_id: string;
  readonly display_name: string;
  readonly start_ns: string;
  readonly end_ns: string;
  readonly session_clock_id: string;
  readonly clocks: readonly {
    readonly id: string;
    readonly source_epoch_ns: string;
    readonly session_epoch_ns: string;
    readonly rate_numerator: number;
    readonly rate_denominator: number;
  }[];
  readonly artifacts: readonly {
    readonly id: string;
    readonly media_type: string;
    readonly logical_key: string;
    readonly size_bytes: number;
    readonly sha256: string;
  }[];
  readonly calibrations: readonly {
    readonly id: string;
    readonly kind: string;
    readonly artifact_id: string;
  }[];
  readonly streams: readonly {
    readonly id: string;
    readonly kind: StreamKind;
    readonly clock_id: string;
    readonly start_ns: string;
    readonly end_ns: string;
    readonly sample_count: number;
    readonly schema_ref: string;
    readonly artifact_ids: readonly string[];
    readonly calibration_ids: readonly string[];
    readonly gaps: readonly {
      readonly start_ns: string;
      readonly end_ns: string;
      readonly reason: StreamGap["reason"];
    }[];
  }[];
  readonly provenance: {
    readonly source_type: string;
    readonly source_uri: string;
    readonly source_sha256: string;
    readonly adapter: string;
    readonly adapter_version: string;
  };
}

export class ManifestValidationError extends Error {
  public constructor(
    message: string,
    public readonly path: string
  ) {
    super(`${path}: ${message}`);
    this.name = "ManifestValidationError";
  }
}

function fail(path: string, message: string): never {
  throw new ManifestValidationError(message, path);
}

function record(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return fail(path, "must be an object");
  }
  return value as Record<string, unknown>;
}

function string(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length === 0) {
    return fail(path, "must be a non-empty string");
  }
  return value;
}

function array(value: unknown, path: string): readonly unknown[] {
  if (!Array.isArray(value)) return fail(path, "must be an array");
  return value;
}

function integer(value: unknown, path: string, minimum = 0): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum) {
    return fail(
      path,
      `must be a safe integer greater than or equal to ${String(minimum)}`
    );
  }
  return value as number;
}

function identifierSet(
  values: readonly { readonly id: string }[],
  path: string
): Set<string> {
  const ids = new Set<string>();
  for (const value of values) {
    if (ids.has(value.id)) fail(path, `contains duplicate id ${value.id}`);
    ids.add(value.id);
  }
  return ids;
}

function referenceList(value: unknown, path: string): readonly string[] {
  return array(value, path).map((entry, index) =>
    string(entry, `${path}[${String(index)}]`)
  );
}

export function timestampNs(
  value: string | bigint,
  path = "timestamp_ns"
): TimestampNs {
  const text = typeof value === "bigint" ? value.toString() : value;
  if (!DECIMAL_INTEGER.test(text))
    fail(path, "must be a canonical decimal integer string");
  const parsed = BigInt(text);
  if (parsed < MIN_I64 || parsed > MAX_I64)
    fail(path, "must fit in a signed 64-bit integer");
  return parsed;
}

function timeRange(value: Record<string, unknown>, path: string): TimeRange {
  const startNs = timestampNs(
    string(value.start_ns, `${path}.start_ns`),
    `${path}.start_ns`
  );
  const endNs = timestampNs(
    string(value.end_ns, `${path}.end_ns`),
    `${path}.end_ns`
  );
  if (endNs < startNs)
    fail(path, "end_ns must be greater than or equal to start_ns");
  return { startNs, endNs };
}

function oneOf<T extends string>(
  value: unknown,
  allowed: readonly T[],
  path: string
): T {
  const parsed = string(value, path);
  if (!allowed.includes(parsed as T))
    fail(path, `must be one of ${allowed.join(", ")}`);
  return parsed as T;
}

export function parseManifest(value: unknown): CaptureSessionManifest {
  const root = record(value, "manifest");
  const schemaVersion = string(root.schema_version, "schema_version");
  if (schemaVersion !== CAPTURE_MANIFEST_SCHEMA_VERSION) {
    fail("schema_version", `unsupported schema version ${schemaVersion}`);
  }
  const range = timeRange(root, "manifest");

  const clocks = array(root.clocks, "clocks").map(
    (entry, index): ClockDefinition => {
      const path = `clocks[${String(index)}]`;
      const clock = record(entry, path);
      return {
        id: string(clock.id, `${path}.id`),
        sourceEpochNs: timestampNs(
          string(clock.source_epoch_ns, `${path}.source_epoch_ns`),
          `${path}.source_epoch_ns`
        ),
        sessionEpochNs: timestampNs(
          string(clock.session_epoch_ns, `${path}.session_epoch_ns`),
          `${path}.session_epoch_ns`
        ),
        rateNumerator: integer(
          clock.rate_numerator,
          `${path}.rate_numerator`,
          1
        ),
        rateDenominator: integer(
          clock.rate_denominator,
          `${path}.rate_denominator`,
          1
        )
      };
    }
  );
  const clockIds = identifierSet(clocks, "clocks");
  const sessionClockId = string(root.session_clock_id, "session_clock_id");
  if (!clockIds.has(sessionClockId))
    fail("session_clock_id", "references an unknown clock");

  const artifacts = array(root.artifacts, "artifacts").map(
    (entry, index): ArtifactDescriptor => {
      const path = `artifacts[${String(index)}]`;
      const artifact = record(entry, path);
      const digest = string(artifact.sha256, `${path}.sha256`);
      if (!SHA256.test(digest))
        fail(`${path}.sha256`, "must be a lowercase SHA-256 digest");
      return {
        id: string(artifact.id, `${path}.id`),
        mediaType: string(artifact.media_type, `${path}.media_type`),
        logicalKey: string(artifact.logical_key, `${path}.logical_key`),
        sizeBytes: integer(artifact.size_bytes, `${path}.size_bytes`),
        sha256: digest
      };
    }
  );
  const artifactIds = identifierSet(artifacts, "artifacts");

  const calibrations = array(root.calibrations, "calibrations").map(
    (entry, index): CalibrationReference => {
      const path = `calibrations[${String(index)}]`;
      const calibration = record(entry, path);
      const artifactId = string(calibration.artifact_id, `${path}.artifact_id`);
      if (!artifactIds.has(artifactId))
        fail(`${path}.artifact_id`, "references an unknown artifact");
      return {
        id: string(calibration.id, `${path}.id`),
        kind: string(calibration.kind, `${path}.kind`),
        artifactId
      };
    }
  );
  const calibrationIds = identifierSet(calibrations, "calibrations");

  const streams = array(root.streams, "streams").map(
    (entry, index): CaptureStream => {
      const path = `streams[${String(index)}]`;
      const stream = record(entry, path);
      const streamRange = timeRange(stream, path);
      if (
        streamRange.startNs < range.startNs ||
        streamRange.endNs > range.endNs
      ) {
        fail(path, "range must be contained by the session range");
      }
      const clockId = string(stream.clock_id, `${path}.clock_id`);
      if (!clockIds.has(clockId))
        fail(`${path}.clock_id`, "references an unknown clock");
      const streamArtifactIds = referenceList(
        stream.artifact_ids,
        `${path}.artifact_ids`
      );
      for (const id of streamArtifactIds) {
        if (!artifactIds.has(id))
          fail(`${path}.artifact_ids`, `references unknown artifact ${id}`);
      }
      const streamCalibrationIds = referenceList(
        stream.calibration_ids,
        `${path}.calibration_ids`
      );
      for (const id of streamCalibrationIds) {
        if (!calibrationIds.has(id)) {
          fail(
            `${path}.calibration_ids`,
            `references unknown calibration ${id}`
          );
        }
      }
      let previousGapEnd: bigint | undefined;
      const gaps = array(stream.gaps, `${path}.gaps`).map(
        (gapEntry, gapIndex): StreamGap => {
          const gapPath = `${path}.gaps[${String(gapIndex)}]`;
          const gap = timeRange(record(gapEntry, gapPath), gapPath);
          if (
            gap.startNs < streamRange.startNs ||
            gap.endNs > streamRange.endNs
          ) {
            fail(gapPath, "range must be contained by the stream range");
          }
          if (previousGapEnd !== undefined && gap.startNs < previousGapEnd) {
            fail(gapPath, "gaps must be ordered and non-overlapping");
          }
          previousGapEnd = gap.endNs;
          return {
            ...gap,
            reason: oneOf(
              record(gapEntry, gapPath).reason,
              ["missing", "corrupt", "clock_discontinuity"] as const,
              `${gapPath}.reason`
            )
          };
        }
      );
      return {
        ...streamRange,
        id: string(stream.id, `${path}.id`),
        kind: oneOf(
          stream.kind,
          ["video", "imu", "pose", "event", "telemetry"] as const,
          `${path}.kind`
        ),
        clockId,
        sampleCount: integer(stream.sample_count, `${path}.sample_count`),
        schemaRef: string(stream.schema_ref, `${path}.schema_ref`),
        artifactIds: streamArtifactIds,
        calibrationIds: streamCalibrationIds,
        gaps
      };
    }
  );
  identifierSet(streams, "streams");

  const provenanceValue = record(root.provenance, "provenance");
  const sourceSha256 = string(
    provenanceValue.source_sha256,
    "provenance.source_sha256"
  );
  if (!SHA256.test(sourceSha256)) {
    fail("provenance.source_sha256", "must be a lowercase SHA-256 digest");
  }

  return {
    ...range,
    schemaVersion: CAPTURE_MANIFEST_SCHEMA_VERSION,
    sessionId: string(root.session_id, "session_id"),
    displayName: string(root.display_name, "display_name"),
    sessionClockId,
    clocks,
    artifacts,
    calibrations,
    streams,
    provenance: {
      sourceType: string(provenanceValue.source_type, "provenance.source_type"),
      sourceUri: string(provenanceValue.source_uri, "provenance.source_uri"),
      sourceSha256,
      adapter: string(provenanceValue.adapter, "provenance.adapter"),
      adapterVersion: string(
        provenanceValue.adapter_version,
        "provenance.adapter_version"
      )
    }
  };
}
