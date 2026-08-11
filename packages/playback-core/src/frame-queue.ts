export interface QueuedFrame {
  readonly timestampUs: number;
  close(): void;
}

/** Timestamp-ordered decoded-frame queue with deterministic resource eviction. */
export class BoundedFrameQueue<T extends QueuedFrame> {
  readonly #capacity: number;
  readonly #frames: T[] = [];

  constructor(capacity = 12) {
    if (!Number.isInteger(capacity) || capacity < 1)
      throw new RangeError("frame queue capacity must be a positive integer");
    this.#capacity = capacity;
  }

  get size(): number {
    return this.#frames.length;
  }

  push(frame: T): void {
    const index = this.#frames.findIndex(
      (candidate) => candidate.timestampUs > frame.timestampUs
    );
    if (index === -1) this.#frames.push(frame);
    else this.#frames.splice(index, 0, frame);
    while (this.#frames.length > this.#capacity) this.#frames.shift()?.close();
  }

  takeAtOrBefore(timestampUs: number): T | undefined {
    let index = -1;
    for (let candidate = 0; candidate < this.#frames.length; candidate += 1) {
      if ((this.#frames[candidate]?.timestampUs ?? Infinity) > timestampUs)
        break;
      index = candidate;
    }
    if (index < 0) return undefined;
    const stale = this.#frames.splice(0, index);
    for (const frame of stale) frame.close();
    return this.#frames.shift();
  }

  clear(): void {
    for (const frame of this.#frames.splice(0)) frame.close();
  }
}
