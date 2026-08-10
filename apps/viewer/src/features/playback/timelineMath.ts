import type { StreamGap, TimestampNs } from "@aeromaint/contracts";

export interface TimelineRange {
  readonly startNs: TimestampNs;
  readonly endNs: TimestampNs;
}

export function clampTime(
  timeNs: TimestampNs,
  range: TimelineRange
): TimestampNs {
  if (timeNs < range.startNs) return range.startNs;
  if (timeNs > range.endNs) return range.endNs;
  return timeNs;
}

export function timeToRatio(timeNs: TimestampNs, range: TimelineRange): number {
  const duration = range.endNs - range.startNs;
  if (duration <= 0n) return 0;
  const offset = clampTime(timeNs, range) - range.startNs;
  return Number(offset) / Number(duration);
}

export function ratioToTime(ratio: number, range: TimelineRange): TimestampNs {
  const safeRatio = Math.max(0, Math.min(1, ratio));
  const duration = range.endNs - range.startNs;
  return range.startNs + BigInt(Math.round(Number(duration) * safeRatio));
}

export function gapAt(
  timeNs: TimestampNs,
  gaps: readonly StreamGap[]
): StreamGap | undefined {
  return gaps.find((gap) => timeNs >= gap.startNs && timeNs < gap.endNs);
}

export function stepTime(
  currentNs: TimestampNs,
  deltaNs: bigint,
  range: TimelineRange
): TimestampNs {
  return clampTime(currentNs + deltaNs, range);
}

export function formatSessionTime(
  timeNs: TimestampNs,
  startNs: TimestampNs
): string {
  const elapsed = Number(timeNs - startNs) / 1_000_000_000;
  const minutes = Math.floor(Math.max(0, elapsed) / 60);
  const seconds = Math.max(0, elapsed) - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${seconds.toFixed(3).padStart(6, "0")}`;
}
