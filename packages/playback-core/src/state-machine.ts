import type { TimeRange, TimestampNs } from "@aeromaint/contracts";

import type { PlaybackClock } from "./clock.js";

export type PlaybackStatus =
  | "idle"
  | "loading"
  | "ready"
  | "playing"
  | "paused"
  | "seeking"
  | "ended"
  | "error";

export interface StreamTimeline {
  readonly id: string;
  readonly gaps?: readonly TimeRange[];
}

export interface PlaybackSource {
  readonly startNs: TimestampNs;
  readonly endNs: TimestampNs;
  readonly streams: readonly StreamTimeline[];
  readonly masterStreamId: string;
}

export interface PlaybackState {
  readonly status: PlaybackStatus;
  readonly currentTimeNs: TimestampNs;
  readonly playbackRate: number;
  readonly loopRange: TimeRange | null;
  readonly masterStreamId: string | null;
  readonly buffers: Readonly<Record<string, readonly TimeRange[]>>;
  readonly driftNs: Readonly<Record<string, TimestampNs>>;
  readonly seekGeneration: number;
  readonly source: PlaybackSource | null;
  readonly error: string | null;
  readonly resumeAfterLoading: boolean;
  readonly resumeAfterSeek: boolean;
  readonly clockAnchorNs: bigint | null;
  readonly playheadAnchorNs: TimestampNs;
}

export type PlaybackAction =
  | {
      readonly type: "load";
      readonly source: PlaybackSource;
      readonly nowNs: bigint;
    }
  | { readonly type: "loaded"; readonly nowNs: bigint }
  | { readonly type: "play"; readonly nowNs: bigint }
  | { readonly type: "pause"; readonly nowNs: bigint }
  | { readonly type: "tick"; readonly nowNs: bigint }
  | { readonly type: "set-rate"; readonly rate: number; readonly nowNs: bigint }
  | {
      readonly type: "set-loop";
      readonly range: TimeRange | null;
      readonly nowNs: bigint;
    }
  | {
      readonly type: "set-master";
      readonly streamId: string;
      readonly nowNs: bigint;
    }
  | {
      readonly type: "set-buffer";
      readonly streamId: string;
      readonly ranges: readonly TimeRange[];
      readonly nowNs: bigint;
    }
  | {
      readonly type: "set-drift";
      readonly streamId: string;
      readonly driftNs: TimestampNs;
    }
  | {
      readonly type: "seek";
      readonly targetNs: TimestampNs;
      readonly nowNs: bigint;
    }
  | {
      readonly type: "seeked";
      readonly generation: number;
      readonly actualNs?: TimestampNs;
      readonly nowNs: bigint;
    }
  | {
      readonly type: "seek-failed";
      readonly generation: number;
      readonly message: string;
    }
  | { readonly type: "fail"; readonly message: string }
  | { readonly type: "reset" };

type WithoutClock<T> = T extends { readonly nowNs: bigint }
  ? Omit<T, "nowNs">
  : T;
export type ClockedPlaybackAction = WithoutClock<PlaybackAction>;

export const initialPlaybackState: PlaybackState = {
  status: "idle",
  currentTimeNs: 0n,
  playbackRate: 1,
  loopRange: null,
  masterStreamId: null,
  buffers: {},
  driftNs: {},
  seekGeneration: 0,
  source: null,
  error: null,
  resumeAfterLoading: false,
  resumeAfterSeek: false,
  clockAnchorNs: null,
  playheadAnchorNs: 0n
};

const RATE_SCALE = 1_000_000_000n;

function assertRange(range: TimeRange, label: string): void {
  if (range.endNs < range.startNs)
    throw new RangeError(`${label} end must not precede start`);
}

function normalizedRanges(ranges: readonly TimeRange[]): readonly TimeRange[] {
  const sorted = ranges
    .map((range) => {
      assertRange(range, "range");
      return { ...range };
    })
    .sort((a, b) =>
      a.startNs < b.startNs ? -1 : a.startNs > b.startNs ? 1 : 0
    );
  const merged: { startNs: bigint; endNs: bigint }[] = [];
  for (const range of sorted) {
    const previous = merged.at(-1);
    if (previous !== undefined && range.startNs <= previous.endNs) {
      if (range.endNs > previous.endNs) previous.endNs = range.endNs;
    } else merged.push({ ...range });
  }
  return merged;
}

function inRange(timeNs: bigint, range: TimeRange): boolean {
  return timeNs >= range.startNs && timeNs <= range.endNs;
}

function clamp(timeNs: bigint, range: TimeRange): bigint {
  return timeNs < range.startNs
    ? range.startNs
    : timeNs > range.endNs
      ? range.endNs
      : timeNs;
}

function stream(
  state: PlaybackState,
  id: string | null
): StreamTimeline | undefined {
  return id === null
    ? undefined
    : state.source?.streams.find((item) => item.id === id);
}

function skipGaps(
  timeNs: bigint,
  timeline: StreamTimeline | undefined
): bigint {
  let result = timeNs;
  for (const gap of timeline?.gaps ?? []) {
    assertRange(gap, "gap");
    if (result >= gap.startNs && result < gap.endNs) result = gap.endNs;
  }
  return result;
}

function isBuffered(state: PlaybackState, timeNs: bigint): boolean {
  const id = state.masterStreamId;
  if (id === null) return true;
  const ranges = state.buffers[id];
  // An unreported buffer is permissive; once reported it is authoritative.
  return ranges === undefined || ranges.some((range) => inRange(timeNs, range));
}

function bufferedUntil(
  state: PlaybackState,
  fromNs: bigint,
  targetNs: bigint
): bigint | null {
  const id = state.masterStreamId;
  if (id === null) return targetNs;
  const ranges = state.buffers[id];
  if (ranges === undefined) return targetNs;
  const containing = ranges.find((range) => inRange(fromNs, range));
  if (containing === undefined) return null;
  return targetNs <= containing.endNs ? targetNs : containing.endNs;
}

function activeRange(state: PlaybackState): TimeRange {
  if (state.source === null) return { startNs: 0n, endNs: 0n };
  return state.loopRange ?? state.source;
}

function advance(state: PlaybackState, nowNs: bigint): PlaybackState {
  if (state.status !== "playing" || state.clockAnchorNs === null) return state;
  if (nowNs < state.clockAnchorNs)
    throw new RangeError("clock must be monotonic");
  const rateFixed = BigInt(Math.round(state.playbackRate * Number(RATE_SCALE)));
  const elapsedNs = ((nowNs - state.clockAnchorNs) * rateFixed) / RATE_SCALE;
  const range = activeRange(state);
  let targetNs = skipGaps(
    state.playheadAnchorNs + elapsedNs,
    stream(state, state.masterStreamId)
  );
  if (state.loopRange !== null && targetNs >= range.endNs) {
    const length = range.endNs - range.startNs;
    targetNs =
      length === 0n
        ? range.startNs
        : range.startNs + ((targetNs - range.startNs) % length);
  } else if (targetNs >= range.endNs) {
    return {
      ...state,
      status: "ended",
      currentTimeNs: range.endNs,
      clockAnchorNs: null,
      playheadAnchorNs: range.endNs
    };
  }
  const availableTarget = bufferedUntil(state, state.currentTimeNs, targetNs);
  if (availableTarget === null || availableTarget !== targetNs) {
    const stalledAt = availableTarget ?? state.currentTimeNs;
    return {
      ...state,
      status: "loading",
      currentTimeNs: stalledAt,
      resumeAfterLoading: true,
      clockAnchorNs: null,
      playheadAnchorNs: stalledAt
    };
  }
  return { ...state, currentTimeNs: targetNs };
}

function withAnchor(state: PlaybackState, nowNs: bigint): PlaybackState {
  return {
    ...state,
    clockAnchorNs: nowNs,
    playheadAnchorNs: state.currentTimeNs
  };
}

function validateSource(source: PlaybackSource): void {
  assertRange(source, "source");
  if (source.streams.length === 0)
    throw new RangeError("source must contain a stream");
  if (!source.streams.some((item) => item.id === source.masterStreamId))
    throw new RangeError("master stream must exist in source");
  const ids = new Set<string>();
  for (const item of source.streams) {
    if (ids.has(item.id)) throw new RangeError(`duplicate stream ${item.id}`);
    ids.add(item.id);
    for (const gap of item.gaps ?? []) assertRange(gap, "gap");
  }
}

export function playbackReducer(
  state: PlaybackState,
  action: PlaybackAction
): PlaybackState {
  switch (action.type) {
    case "reset":
      return initialPlaybackState;
    case "load": {
      validateSource(action.source);
      return {
        ...initialPlaybackState,
        status: "loading",
        currentTimeNs: action.source.startNs,
        playheadAnchorNs: action.source.startNs,
        source: action.source,
        masterStreamId: action.source.masterStreamId,
        clockAnchorNs: action.nowNs
      };
    }
    case "loaded": {
      if (state.status !== "loading" || state.source === null) return state;
      const status = state.resumeAfterLoading ? "playing" : "ready";
      return withAnchor(
        { ...state, status, resumeAfterLoading: false },
        action.nowNs
      );
    }
    case "play": {
      if (
        state.source === null ||
        !["ready", "paused", "ended"].includes(state.status)
      )
        return state;
      const start =
        state.status === "ended"
          ? activeRange(state).startNs
          : state.currentTimeNs;
      return withAnchor(
        {
          ...state,
          status: "playing",
          currentTimeNs: start,
          playheadAnchorNs: start,
          error: null
        },
        action.nowNs
      );
    }
    case "pause": {
      if (state.status !== "playing") return state;
      const advanced = advance(state, action.nowNs);
      return {
        ...advanced,
        status: advanced.status === "ended" ? "ended" : "paused",
        clockAnchorNs: null,
        playheadAnchorNs: advanced.currentTimeNs
      };
    }
    case "tick":
      return advance(state, action.nowNs);
    case "set-rate": {
      if (!Number.isFinite(action.rate) || action.rate <= 0 || action.rate > 16)
        throw new RangeError("playback rate must be finite and in (0, 16]");
      const advanced = advance(state, action.nowNs);
      return withAnchor(
        { ...advanced, playbackRate: action.rate },
        action.nowNs
      );
    }
    case "set-loop": {
      const advanced = advance(state, action.nowNs);
      if (action.range !== null) {
        if (advanced.source === null) return state;
        assertRange(action.range, "loop");
        if (
          action.range.startNs < advanced.source.startNs ||
          action.range.endNs > advanced.source.endNs
        )
          throw new RangeError("loop must be within source bounds");
      }
      const next = { ...advanced, loopRange: action.range };
      return advanced.status === "playing"
        ? withAnchor(next, action.nowNs)
        : next;
    }
    case "set-master": {
      if (!state.source?.streams.some((item) => item.id === action.streamId))
        return state;
      const advanced = advance(state, action.nowNs);
      return advanced.status === "playing"
        ? withAnchor(
            { ...advanced, masterStreamId: action.streamId },
            action.nowNs
          )
        : { ...advanced, masterStreamId: action.streamId };
    }
    case "set-buffer": {
      if (!state.source?.streams.some((item) => item.id === action.streamId))
        return state;
      const buffers = {
        ...state.buffers,
        [action.streamId]: normalizedRanges(action.ranges)
      };
      const next = { ...state, buffers };
      if (
        state.status === "loading" &&
        state.resumeAfterLoading &&
        isBuffered(next, state.currentTimeNs)
      )
        return withAnchor(
          { ...next, status: "playing", resumeAfterLoading: false },
          action.nowNs
        );
      return next;
    }
    case "set-drift": {
      if (!state.source?.streams.some((item) => item.id === action.streamId))
        return state;
      return {
        ...state,
        driftNs: { ...state.driftNs, [action.streamId]: action.driftNs }
      };
    }
    case "seek": {
      if (
        state.source === null ||
        !["ready", "playing", "paused", "ended", "loading", "seeking"].includes(
          state.status
        )
      )
        return state;
      const advanced = advance(state, action.nowNs);
      const target = skipGaps(
        clamp(action.targetNs, activeRange(advanced)),
        stream(advanced, advanced.masterStreamId)
      );
      return {
        ...advanced,
        status: "seeking",
        currentTimeNs: target,
        playheadAnchorNs: target,
        clockAnchorNs: null,
        seekGeneration: state.seekGeneration + 1,
        resumeAfterSeek: state.status === "playing" || state.resumeAfterSeek,
        resumeAfterLoading: false,
        error: null
      };
    }
    case "seeked": {
      if (
        state.status !== "seeking" ||
        action.generation !== state.seekGeneration ||
        state.source === null
      )
        return state;
      const actual = skipGaps(
        clamp(action.actualNs ?? state.currentTimeNs, activeRange(state)),
        stream(state, state.masterStreamId)
      );
      if (!isBuffered(state, actual))
        return {
          ...state,
          status: "loading",
          currentTimeNs: actual,
          playheadAnchorNs: actual,
          resumeAfterLoading: state.resumeAfterSeek,
          resumeAfterSeek: false
        };
      const status = state.resumeAfterSeek ? "playing" : "paused";
      return withAnchor(
        {
          ...state,
          status,
          currentTimeNs: actual,
          playheadAnchorNs: actual,
          resumeAfterSeek: false
        },
        action.nowNs
      );
    }
    case "seek-failed":
      return state.status === "seeking" &&
        action.generation === state.seekGeneration
        ? {
            ...state,
            status: "error",
            error: action.message,
            clockAnchorNs: null,
            resumeAfterSeek: false
          }
        : state;
    case "fail":
      return {
        ...state,
        status: "error",
        error: action.message,
        clockAnchorNs: null,
        resumeAfterLoading: false,
        resumeAfterSeek: false
      };
  }
}

export class PlaybackMachine {
  private value: PlaybackState;
  private readonly listeners = new Set<(state: PlaybackState) => void>();

  public constructor(
    private readonly clock: PlaybackClock,
    initial = initialPlaybackState
  ) {
    this.value = initial;
  }

  public get state(): PlaybackState {
    return this.value;
  }

  public dispatch(
    action: ClockedPlaybackAction | PlaybackAction
  ): PlaybackState {
    const resolved =
      "nowNs" in action
        ? action
        : ({ ...action, nowNs: this.clock.nowNs() } as PlaybackAction);
    const next = playbackReducer(this.value, resolved);
    if (next !== this.value) {
      this.value = next;
      for (const listener of this.listeners) listener(next);
    }
    return next;
  }

  public tick(): PlaybackState {
    return this.dispatch({ type: "tick", nowNs: this.clock.nowNs() });
  }

  public subscribe(listener: (state: PlaybackState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}
