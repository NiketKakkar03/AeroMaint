import { envelopeForViewport } from "@aeromaint/timeline-renderer";

interface EnvelopeRequest {
  readonly id: string;
  readonly timestampsNs: BigInt64Array;
  readonly values: Float64Array;
  readonly startNs: bigint;
  readonly endNs: bigint;
  readonly viewportPixels: number;
}

self.addEventListener("message", (event: MessageEvent<EnvelopeRequest>) => {
  const request = event.data;
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
  self.postMessage({ id: request.id, envelopes });
});

export {};
