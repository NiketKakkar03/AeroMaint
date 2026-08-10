import type { StreamGap, TimestampNs, TimeRange } from "@aeromaint/contracts";

export function clampTimestamp(
  value: TimestampNs,
  range: TimeRange
): TimestampNs {
  if (value < range.startNs) return range.startNs;
  if (value > range.endNs) return range.endNs;
  return value;
}

export function timestampFromUrl(
  search: string,
  range: TimeRange
): TimestampNs {
  const value = new URLSearchParams(search).get("t");
  if (value === null || !/^-?\d+$/.test(value)) return range.startNs;
  try {
    return clampTimestamp(BigInt(value), range);
  } catch {
    return range.startNs;
  }
}

export function urlWithTimestamp(url: URL, timestamp: TimestampNs): string {
  const next = new URL(url);
  next.searchParams.set("t", timestamp.toString());
  return `${next.pathname}${next.search}${next.hash}`;
}

export function timestampInGap(
  timestamp: TimestampNs,
  gaps: readonly StreamGap[]
): StreamGap | undefined {
  return gaps.find((gap) => timestamp >= gap.startNs && timestamp < gap.endNs);
}

export class SeekCoordinator {
  #generation = 0;
  public begin(): number {
    this.#generation += 1;
    return this.#generation;
  }
  public isCurrent(generation: number): boolean {
    return generation === this.#generation;
  }
}
