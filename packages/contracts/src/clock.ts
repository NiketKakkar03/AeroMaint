import type { ClockDefinition, StreamGap, TimestampNs } from "./index.js";

export interface IndexedFrame {
  readonly frameNumber: number;
  readonly presentationNs: TimestampNs;
  readonly keyframe: boolean;
}

function floorDivide(numerator: bigint, denominator: bigint): bigint {
  const quotient = numerator / denominator;
  const remainder = numerator % denominator;
  return remainder !== 0n && numerator < 0n ? quotient - 1n : quotient;
}

export function mapToSessionTime(
  sourceNs: TimestampNs,
  clock: ClockDefinition
): TimestampNs {
  const scaled = floorDivide(
    (sourceNs - clock.sourceEpochNs) * BigInt(clock.rateNumerator),
    BigInt(clock.rateDenominator)
  );
  return clock.sessionEpochNs + scaled;
}

function isInsideGap(timeNs: TimestampNs, gaps: readonly StreamGap[]): boolean {
  return gaps.some((gap) => timeNs >= gap.startNs && timeNs < gap.endNs);
}

export function frameAtOrBefore(
  frames: readonly IndexedFrame[],
  requestedNs: TimestampNs,
  gaps: readonly StreamGap[] = []
): IndexedFrame | undefined {
  if (isInsideGap(requestedNs, gaps)) return undefined;
  let match: IndexedFrame | undefined;
  for (const frame of frames) {
    if (frame.presentationNs > requestedNs) break;
    match = frame;
  }
  return match;
}

export function nearestFrame(
  frames: readonly IndexedFrame[],
  requestedNs: TimestampNs,
  gaps: readonly StreamGap[] = []
): IndexedFrame | undefined {
  if (isInsideGap(requestedNs, gaps)) return undefined;
  let match: IndexedFrame | undefined;
  let distance: bigint | undefined;
  for (const frame of frames) {
    const candidateDistance =
      frame.presentationNs >= requestedNs
        ? frame.presentationNs - requestedNs
        : requestedNs - frame.presentationNs;
    if (distance === undefined || candidateDistance < distance) {
      match = frame;
      distance = candidateDistance;
    }
  }
  return match;
}
