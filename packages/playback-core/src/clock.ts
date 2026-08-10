export interface PlaybackClock {
  nowNs(): bigint;
}

export class SystemMonotonicClock implements PlaybackClock {
  private readonly originMs = performance.now();

  public nowNs(): bigint {
    return BigInt(Math.floor((performance.now() - this.originMs) * 1_000_000));
  }
}

/** Deterministic monotonic clock intended for tests and simulations. */
export class FakeClock implements PlaybackClock {
  private timeNs: bigint;

  public constructor(initialNs = 0n) {
    if (initialNs < 0n) throw new RangeError("clock time cannot be negative");
    this.timeNs = initialNs;
  }

  public nowNs(): bigint {
    return this.timeNs;
  }

  public advanceBy(deltaNs: bigint): void {
    if (deltaNs < 0n)
      throw new RangeError("a monotonic clock cannot go backwards");
    this.timeNs += deltaNs;
  }

  public set(timeNs: bigint): void {
    if (timeNs < this.timeNs)
      throw new RangeError("a monotonic clock cannot go backwards");
    this.timeNs = timeNs;
  }
}
