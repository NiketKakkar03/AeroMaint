export interface TimelineSample {
  readonly timeNs: bigint;
  readonly value: number;
}

export interface TimelineEnvelope {
  readonly startNs: bigint;
  readonly endNs: bigint;
  readonly min: number;
  readonly max: number;
  readonly count: number;
}

/** Produces at most one min/max envelope per viewport pixel. */
export function envelopeForViewport(
  samples: readonly TimelineSample[],
  startNs: bigint,
  endNs: bigint,
  viewportPixels: number
): readonly TimelineEnvelope[] {
  if (!Number.isInteger(viewportPixels) || viewportPixels < 1)
    throw new RangeError("viewportPixels must be a positive integer");
  if (endNs < startNs) throw new RangeError("invalid timeline window");
  const duration = endNs - startNs;
  if (duration === 0n) return [];
  const buckets = new Map<number, TimelineEnvelope>();
  for (const sample of samples) {
    if (sample.timeNs < startNs || sample.timeNs > endNs) continue;
    const offset = sample.timeNs - startNs;
    const bucket = Math.min(
      viewportPixels - 1,
      Number((offset * BigInt(viewportPixels)) / duration)
    );
    const current = buckets.get(bucket);
    const bucketStartNs =
      startNs + (duration * BigInt(bucket)) / BigInt(viewportPixels);
    const bucketEndNs =
      startNs + (duration * BigInt(bucket + 1)) / BigInt(viewportPixels);
    buckets.set(
      bucket,
      current === undefined
        ? {
            startNs: bucketStartNs,
            endNs: bucketEndNs,
            min: sample.value,
            max: sample.value,
            count: 1
          }
        : {
            ...current,
            min: Math.min(current.min, sample.value),
            max: Math.max(current.max, sample.value),
            count: current.count + 1
          }
    );
  }
  return [...buckets.entries()]
    .sort(([a], [b]) => a - b)
    .map(([, value]) => value);
}

export class WindowCache<T> {
  readonly #limit: number;
  readonly #entries = new Map<string, T>();

  constructor(limit = 8) {
    if (!Number.isInteger(limit) || limit < 1)
      throw new RangeError("cache limit must be a positive integer");
    this.#limit = limit;
  }

  get size(): number {
    return this.#entries.size;
  }

  get(key: string): T | undefined {
    const value = this.#entries.get(key);
    if (value !== undefined) {
      this.#entries.delete(key);
      this.#entries.set(key, value);
    }
    return value;
  }

  set(key: string, value: T): string | undefined {
    this.#entries.delete(key);
    this.#entries.set(key, value);
    if (this.#entries.size <= this.#limit) return undefined;
    const oldest = this.#entries.keys().next().value;
    if (oldest !== undefined) this.#entries.delete(oldest);
    return oldest;
  }
}
