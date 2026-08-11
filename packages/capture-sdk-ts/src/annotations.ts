import type { TimestampNs } from "@aeromaint/contracts";

export type AnnotationStatus = "draft" | "approved" | "rejected";
export type AnnotationShape = "point" | "interval";

export interface Annotation {
  readonly id: string;
  readonly sessionId: string;
  readonly streamId?: string;
  readonly startNs: TimestampNs;
  readonly endNs: TimestampNs;
  readonly shape: AnnotationShape;
  readonly kind: string;
  readonly payload: Readonly<Record<string, unknown>>;
  readonly version: number;
  readonly status: AnnotationStatus;
  readonly actor: string;
  readonly provenance: Readonly<Record<string, unknown>>;
  readonly createdAt: string;
  readonly updatedAt: string;
}

export interface AnnotationDraft {
  readonly startNs: TimestampNs;
  readonly endNs?: TimestampNs;
  readonly streamId?: string;
  readonly kind: string;
  readonly payload?: Readonly<Record<string, unknown>>;
  readonly provenance?: Readonly<Record<string, unknown>>;
}

export interface AnnotationUpdate extends AnnotationDraft {
  readonly expectedVersion: number;
}

export interface AnnotationReview {
  readonly expectedVersion: number;
  readonly decision: "approved" | "rejected";
  readonly comment?: string;
}

export interface AnnotationAuditEvent {
  readonly id: number;
  readonly occurredAt: string;
  readonly actor: string;
  readonly action: string;
  readonly payload: Readonly<Record<string, unknown>>;
}

function object(value: unknown, name: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new TypeError(`${name} must be an object`);
  return value as Record<string, unknown>;
}

function text(value: unknown, name: string): string {
  if (typeof value !== "string" || value.length === 0)
    throw new TypeError(`${name} must be a non-empty string`);
  return value;
}

export function parseAnnotation(value: unknown): Annotation {
  const item = object(value, "Annotation");
  const startNs = BigInt(text(item.start_ns, "Annotation start_ns"));
  const endNs = BigInt(text(item.end_ns, "Annotation end_ns"));
  const status = text(item.status, "Annotation status") as AnnotationStatus;
  if (!["draft", "approved", "rejected"].includes(status))
    throw new TypeError("Annotation status is invalid");
  const streamId =
    typeof item.stream_id === "string" ? item.stream_id : undefined;
  return {
    id: text(item.id, "Annotation id"),
    sessionId: text(item.session_id, "Annotation session_id"),
    ...(streamId === undefined ? {} : { streamId }),
    startNs,
    endNs,
    shape: startNs === endNs ? "point" : "interval",
    kind: text(item.kind, "Annotation kind"),
    payload: object(item.payload ?? {}, "Annotation payload"),
    version: Number(item.version),
    status,
    actor: text(item.actor, "Annotation actor"),
    provenance: object(item.provenance ?? {}, "Annotation provenance"),
    createdAt: text(item.created_at, "Annotation created_at"),
    updatedAt: text(item.updated_at, "Annotation updated_at")
  };
}

export function annotationBody(
  value: AnnotationDraft
): Record<string, unknown> {
  return {
    start_ns: value.startNs.toString(),
    ...(value.endNs === undefined ? {} : { end_ns: value.endNs.toString() }),
    ...(value.streamId === undefined ? {} : { stream_id: value.streamId }),
    kind: value.kind,
    payload: value.payload ?? {},
    provenance: value.provenance ?? {}
  };
}
