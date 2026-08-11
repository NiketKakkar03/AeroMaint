export const MODEL_TRACK_SCHEMA_VERSION = "1.0.0" as const;

export type PredictionStatus = "ok" | "insufficient_history" | "ood";
export type AnomalySeverity = "none" | "warning" | "critical";

export interface ModelVersions {
  readonly model: string;
  readonly features: string;
  readonly data: string;
  readonly code: string;
}

export interface FeatureAttribution {
  readonly feature: string;
  readonly contribution: number;
  readonly unit: string;
}

export interface ModelTrackPoint {
  readonly timestampNs: bigint;
  readonly status: PredictionStatus;
  readonly rul: number | null;
  readonly rulUnit: "cycles" | "hours";
  readonly interval: readonly [number, number] | null;
  readonly horizon: number;
  readonly horizonUnit: "cycles" | "hours";
  readonly anomalyScore: number | null;
  readonly anomalySeverity: AnomalySeverity;
  readonly reason?: string;
  readonly oodFeatures: readonly string[];
  readonly attribution: readonly FeatureAttribution[];
}

export interface ModelTrack {
  readonly schemaVersion: typeof MODEL_TRACK_SCHEMA_VERSION;
  readonly artifactId: string;
  readonly engineId: string;
  readonly sessionId: string;
  readonly createdAt: string;
  readonly versions: ModelVersions;
  readonly points: readonly ModelTrackPoint[];
}

export class ModelTrackValidationError extends Error {
  public constructor(
    message: string,
    public readonly path: string
  ) {
    super(`${path}: ${message}`);
    this.name = "ModelTrackValidationError";
  }
}

function fail(path: string, message: string): never {
  throw new ModelTrackValidationError(message, path);
}
function object(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    return fail(path, "must be an object");
  return value as Record<string, unknown>;
}
function text(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length === 0)
    return fail(path, "must be a non-empty string");
  return value;
}
function finite(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value))
    return fail(path, "must be finite");
  return value;
}
function choice<T extends string>(
  value: unknown,
  values: readonly T[],
  path: string
): T {
  const result = text(value, path);
  if (!values.includes(result as T))
    return fail(path, `must be one of ${values.join(", ")}`);
  return result as T;
}

export function parseModelTrack(value: unknown): ModelTrack {
  const root = object(value, "model_track");
  if (root.schema_version !== MODEL_TRACK_SCHEMA_VERSION)
    fail(
      "schema_version",
      `unsupported schema version ${String(root.schema_version)}`
    );
  const versionsValue = object(root.versions, "versions");
  const pointsValue = root.points;
  if (!Array.isArray(pointsValue)) fail("points", "must be an array");
  let previous: bigint | undefined;
  const points = pointsValue.map((entry, index): ModelTrackPoint => {
    const path = `points[${String(index)}]`;
    const point = object(entry, path);
    const timestampNs = BigInt(
      text(point.timestamp_ns, `${path}.timestamp_ns`)
    );
    if (previous !== undefined && timestampNs < previous)
      fail(path, "must be time ordered");
    previous = timestampNs;
    const intervalValue = point.interval;
    const interval: readonly [number, number] | null =
      intervalValue === null
        ? null
        : Array.isArray(intervalValue) && intervalValue.length === 2
          ? [
              finite(intervalValue[0], `${path}.interval[0]`),
              finite(intervalValue[1], `${path}.interval[1]`)
            ]
          : fail(`${path}.interval`, "must be null or a two-number tuple");
    const attributionValue = point.attribution;
    if (!Array.isArray(attributionValue))
      fail(`${path}.attribution`, "must be an array");
    const ood = point.ood_features;
    if (!Array.isArray(ood) || !ood.every((item) => typeof item === "string"))
      fail(`${path}.ood_features`, "must be a string array");
    return {
      timestampNs,
      status: choice(
        point.status,
        ["ok", "insufficient_history", "ood"] as const,
        `${path}.status`
      ),
      rul: point.rul === null ? null : finite(point.rul, `${path}.rul`),
      rulUnit: choice(
        point.rul_unit,
        ["cycles", "hours"] as const,
        `${path}.rul_unit`
      ),
      interval,
      horizon: finite(point.horizon, `${path}.horizon`),
      horizonUnit: choice(
        point.horizon_unit,
        ["cycles", "hours"] as const,
        `${path}.horizon_unit`
      ),
      anomalyScore:
        point.anomaly_score === null
          ? null
          : finite(point.anomaly_score, `${path}.anomaly_score`),
      anomalySeverity: choice(
        point.anomaly_severity,
        ["none", "warning", "critical"] as const,
        `${path}.anomaly_severity`
      ),
      ...(typeof point.reason === "string" ? { reason: point.reason } : {}),
      oodFeatures: ood,
      attribution: attributionValue.map((item, attributionIndex) => {
        const attribution = object(
          item,
          `${path}.attribution[${String(attributionIndex)}]`
        );
        return {
          feature: text(attribution.feature, `${path}.attribution.feature`),
          contribution: finite(
            attribution.contribution,
            `${path}.attribution.contribution`
          ),
          unit: text(attribution.unit, `${path}.attribution.unit`)
        };
      })
    };
  });
  return {
    schemaVersion: MODEL_TRACK_SCHEMA_VERSION,
    artifactId: text(root.artifact_id, "artifact_id"),
    engineId: text(root.engine_id, "engine_id"),
    sessionId: text(root.session_id, "session_id"),
    createdAt: text(root.created_at, "created_at"),
    versions: {
      model: text(versionsValue.model, "versions.model"),
      features: text(versionsValue.features, "versions.features"),
      data: text(versionsValue.data, "versions.data"),
      code: text(versionsValue.code, "versions.code")
    },
    points
  };
}
