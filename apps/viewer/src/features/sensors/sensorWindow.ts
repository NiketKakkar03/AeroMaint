export interface SensorWindow {
  readonly visibleStartNs: bigint;
  readonly visibleEndNs: bigint;
  readonly requestStartNs: bigint;
  readonly requestEndNs: bigint;
}

export function sensorWindow(
  sessionStartNs: bigint,
  sessionEndNs: bigint,
  playheadNs: bigint,
  zoom: number,
  prefetchRatio = 0.2
): SensorWindow {
  if (!Number.isFinite(zoom) || zoom < 1)
    throw new RangeError("zoom must be finite and at least one");
  if (sessionEndNs < sessionStartNs)
    throw new RangeError("session end must not precede start");
  const durationNs = sessionEndNs - sessionStartNs;
  const visibleDurationNs =
    durationNs === 0n ? 0n : durationNs / BigInt(Math.max(1, Math.round(zoom)));
  const bucketNs = visibleDurationNs > 1n ? visibleDurationNs / 2n : 1n;
  const clampedPlayhead =
    playheadNs < sessionStartNs
      ? sessionStartNs
      : playheadNs > sessionEndNs
        ? sessionEndNs
        : playheadNs;
  const bucket = (clampedPlayhead - sessionStartNs) / bucketNs;
  let visibleStartNs =
    sessionStartNs + bucket * bucketNs - visibleDurationNs / 2n;
  if (visibleStartNs < sessionStartNs) visibleStartNs = sessionStartNs;
  let visibleEndNs = visibleStartNs + visibleDurationNs;
  if (visibleEndNs > sessionEndNs) {
    visibleEndNs = sessionEndNs;
    visibleStartNs = sessionEndNs - visibleDurationNs;
  }
  const prefetchNs = BigInt(
    Math.round(Number(visibleDurationNs) * Math.max(0, prefetchRatio))
  );
  return {
    visibleStartNs,
    visibleEndNs,
    requestStartNs:
      visibleStartNs - prefetchNs < sessionStartNs
        ? sessionStartNs
        : visibleStartNs - prefetchNs,
    requestEndNs:
      visibleEndNs + prefetchNs > sessionEndNs
        ? sessionEndNs
        : visibleEndNs + prefetchNs
  };
}
