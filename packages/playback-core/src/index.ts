import type { TimestampNs } from "@aeromaint/contracts";

export type PlaybackStatus =
  | "idle"
  | "loading"
  | "ready"
  | "playing"
  | "paused"
  | "seeking"
  | "ended"
  | "error";

export interface PlaybackState {
  readonly status: PlaybackStatus;
  readonly currentTimeNs: TimestampNs;
  readonly playbackRate: number;
  readonly seekGeneration: number;
}

export const initialPlaybackState: PlaybackState = {
  status: "idle",
  currentTimeNs: 0n,
  playbackRate: 1,
  seekGeneration: 0
};
