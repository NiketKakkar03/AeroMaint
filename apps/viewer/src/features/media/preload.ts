export interface PreloadCandidate {
  readonly timestampNs: bigint;
  readonly src: string;
}

export function boundedPreloadWindow(
  candidates: readonly PreloadCandidate[],
  playheadNs: bigint,
  limit = 4
): readonly PreloadCandidate[] {
  return candidates
    .filter((candidate) => candidate.timestampNs >= playheadNs)
    .slice()
    .sort((a, b) =>
      a.timestampNs < b.timestampNs ? -1 : a.timestampNs > b.timestampNs ? 1 : 0
    )
    .slice(0, Math.max(0, limit));
}
