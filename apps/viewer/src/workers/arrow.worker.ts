import { envelopeForViewport } from "@aeromaint/timeline-renderer";
import { parseArrowVectorStream } from "./arrow-ipc.js";

export interface EnvelopeRequest {
  readonly type: "envelope";
  readonly id: string;
  readonly timestampsNs: BigInt64Array;
  readonly values: Float64Array;
  readonly startNs: bigint;
  readonly endNs: bigint;
  readonly viewportPixels: number;
}

export interface ArrowRequest {
  readonly type: "arrow";
  readonly id: string;
  readonly buffer: ArrayBuffer;
}

export interface VectorEnvelopeRequest {
  readonly type: "vector-envelope";
  readonly id: string;
  readonly timestampsNs: BigInt64Array;
  readonly x: Float64Array;
  readonly y: Float64Array;
  readonly z: Float64Array;
  readonly startNs: bigint;
  readonly endNs: bigint;
  readonly viewportPixels: number;
}

export type ArrowWorkerRequest =
  EnvelopeRequest | ArrowRequest | VectorEnvelopeRequest;

export type ArrowWorkerResponse =
  | {
      readonly type: "envelope";
      readonly id: string;
      readonly envelopes: ReturnType<typeof envelopeForViewport>;
    }
  | {
      readonly type: "samples";
      readonly id: string;
      readonly columns: ReturnType<typeof parseArrowVectorStream>;
    }
  | {
      readonly type: "vector-envelope";
      readonly id: string;
      readonly axes: readonly [
        ReturnType<typeof envelopeForViewport>,
        ReturnType<typeof envelopeForViewport>,
        ReturnType<typeof envelopeForViewport>
      ];
    }
  | { readonly type: "error"; readonly id: string; readonly message: string };

self.addEventListener("message", (event: MessageEvent<ArrowWorkerRequest>) => {
  const request = event.data;
  if (request.type === "arrow") {
    try {
      const columns = parseArrowVectorStream(request.buffer);
      self.postMessage(
        {
          type: "samples",
          id: request.id,
          columns
        } satisfies ArrowWorkerResponse,
        {
          transfer: [
            columns.timestampsNs.buffer,
            columns.x.buffer,
            columns.y.buffer,
            columns.z.buffer
          ]
        }
      );
    } catch (error) {
      self.postMessage({
        type: "error",
        id: request.id,
        message: error instanceof Error ? error.message : String(error)
      } satisfies ArrowWorkerResponse);
    }
    return;
  }
  if (request.type === "vector-envelope") {
    const axes = ([request.x, request.y, request.z] as const).map((values) => {
      const length = Math.min(request.timestampsNs.length, values.length);
      const samples = Array.from({ length }, (_, index) => ({
        timeNs: request.timestampsNs[index] ?? 0n,
        value: values[index] ?? Number.NaN
      }));
      return envelopeForViewport(
        samples,
        request.startNs,
        request.endNs,
        request.viewportPixels
      );
    }) as [
      ReturnType<typeof envelopeForViewport>,
      ReturnType<typeof envelopeForViewport>,
      ReturnType<typeof envelopeForViewport>
    ];
    self.postMessage({
      type: "vector-envelope",
      id: request.id,
      axes
    } satisfies ArrowWorkerResponse);
    return;
  }
  const length = Math.min(request.timestampsNs.length, request.values.length);
  const samples = Array.from({ length }, (_, index) => ({
    timeNs: request.timestampsNs[index] ?? 0n,
    value: request.values[index] ?? Number.NaN
  }));
  const envelopes = envelopeForViewport(
    samples,
    request.startNs,
    request.endNs,
    request.viewportPixels
  );
  self.postMessage({
    type: "envelope",
    id: request.id,
    envelopes
  } satisfies ArrowWorkerResponse);
});

export {};
