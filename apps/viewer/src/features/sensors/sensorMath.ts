import type { StreamGap } from "@aeromaint/contracts";

export interface VectorSample {
  readonly timeNs: bigint;
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

export interface PoseSample extends VectorSample {
  readonly rollDeg: number;
  readonly pitchDeg: number;
  readonly yawDeg: number;
}

export type VectorAxis = "x" | "y" | "z";

export function sampleSegments<T extends VectorSample>(
  samples: readonly T[],
  gaps: readonly StreamGap[]
): readonly (readonly T[])[] {
  const segments: T[][] = [];
  for (const sample of samples) {
    const inGap = gaps.some(
      (gap) => sample.timeNs >= gap.startNs && sample.timeNs < gap.endNs
    );
    if (inGap) continue;
    const previous = segments.at(-1)?.at(-1);
    const crossesGap =
      previous !== undefined &&
      gaps.some(
        (gap) => previous.timeNs < gap.startNs && sample.timeNs >= gap.endNs
      );
    if (previous === undefined || crossesGap) segments.push([]);
    segments.at(-1)?.push(sample);
  }
  return segments;
}

export function closestSample<T extends VectorSample>(
  samples: readonly T[],
  timeNs: bigint
): T | undefined {
  return samples.reduce<T | undefined>((closest, sample) => {
    if (closest === undefined) return sample;
    const distance =
      sample.timeNs > timeNs ? sample.timeNs - timeNs : timeNs - sample.timeNs;
    const closestDistance =
      closest.timeNs > timeNs
        ? closest.timeNs - timeNs
        : timeNs - closest.timeNs;
    return distance < closestDistance ? sample : closest;
  }, undefined);
}

export function valueExtent(
  samples: readonly VectorSample[]
): readonly [number, number] {
  const values = samples.flatMap((sample) => [sample.x, sample.y, sample.z]);
  if (values.length === 0) return [-1, 1];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return [min - 1, max + 1];
  const padding = (max - min) * 0.08;
  return [min - padding, max + padding];
}
