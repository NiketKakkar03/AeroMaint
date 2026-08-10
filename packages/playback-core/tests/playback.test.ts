import { describe, expect, it } from "vitest";

import {
  FakeClock,
  PlaybackMachine,
  initialPlaybackState,
  playbackReducer,
  type PlaybackAction,
  type PlaybackSource,
  type PlaybackState
} from "../src/index.js";

const source: PlaybackSource = {
  startNs: 1_000_000_000_000_000_001n,
  endNs: 1_000_000_010_000_000_001n,
  masterStreamId: "video",
  streams: [
    {
      id: "video",
      gaps: [
        {
          startNs: 1_000_000_004_000_000_001n,
          endNs: 1_000_000_005_000_000_001n
        }
      ]
    },
    { id: "imu" }
  ]
};

function reduce(actions: readonly PlaybackAction[]): PlaybackState {
  return actions.reduce(playbackReducer, initialPlaybackState);
}

describe("playback transitions", () => {
  it.each([
    [
      "idle ignores play",
      initialPlaybackState,
      { type: "play", nowNs: 0n } as const
    ],
    [
      "idle ignores pause",
      initialPlaybackState,
      { type: "pause", nowNs: 0n } as const
    ],
    [
      "ready ignores loaded",
      reduce([
        { type: "load", source, nowNs: 0n },
        { type: "loaded", nowNs: 0n }
      ]),
      { type: "loaded", nowNs: 1n } as const
    ]
  ])("%s", (_name, state, action) => {
    expect(playbackReducer(state, action)).toBe(state);
  });

  it("moves through load, ready, play, pause, and end deterministically", () => {
    const state = reduce([
      { type: "load", source, nowNs: 0n },
      { type: "loaded", nowNs: 1n },
      { type: "play", nowNs: 2n },
      { type: "pause", nowNs: 1_000_000_002n },
      { type: "play", nowNs: 2_000_000_000n },
      { type: "tick", nowNs: 20_000_000_000n }
    ]);
    expect(state.status).toBe("ended");
    expect(state.currentTimeNs).toBe(source.endNs);
  });

  it("validates rates and source/master invariants", () => {
    expect(() =>
      playbackReducer(initialPlaybackState, {
        type: "set-rate",
        rate: 0,
        nowNs: 0n
      })
    ).toThrow(RangeError);
    expect(() =>
      playbackReducer(initialPlaybackState, {
        type: "load",
        source: { ...source, masterStreamId: "missing" },
        nowNs: 0n
      })
    ).toThrow(RangeError);
  });
});

describe("nanosecond clock behavior", () => {
  it("preserves bigint precision and applies rate changes from a fresh anchor", () => {
    const clock = new FakeClock(9_000_000_000_000_000_000n);
    const machine = new PlaybackMachine(clock);
    machine.dispatch({ type: "load", source });
    machine.dispatch({ type: "loaded" });
    machine.dispatch({ type: "play" });
    clock.advanceBy(3n);
    machine.tick();
    expect(machine.state.currentTimeNs).toBe(source.startNs + 3n);
    machine.dispatch({ type: "set-rate", rate: 0.5 });
    clock.advanceBy(10n);
    machine.tick();
    expect(machine.state.currentTimeNs).toBe(source.startNs + 8n);
  });

  it("rejects a clock moving backwards", () => {
    const playing = reduce([
      { type: "load", source, nowNs: 10n },
      { type: "loaded", nowNs: 10n },
      { type: "play", nowNs: 10n }
    ]);
    expect(() => playbackReducer(playing, { type: "tick", nowNs: 9n })).toThrow(
      "monotonic"
    );
  });
});

describe("gaps, buffers, loops, and master stream", () => {
  it("skips a master-stream gap but not a non-master gap", () => {
    const beforeGap = source.streams[0]!.gaps![0]!.startNs - 1n;
    const base = reduce([
      { type: "load", source, nowNs: 0n },
      { type: "loaded", nowNs: 0n },
      { type: "seek", targetNs: beforeGap, nowNs: 0n },
      { type: "seeked", generation: 1, nowNs: 0n },
      { type: "play", nowNs: 0n }
    ]);
    expect(
      playbackReducer(base, { type: "tick", nowNs: 2n }).currentTimeNs
    ).toBe(source.streams[0]!.gaps![0]!.endNs);
    const imuMaster = playbackReducer(base, {
      type: "set-master",
      streamId: "imu",
      nowNs: 0n
    });
    expect(
      playbackReducer(imuMaster, { type: "tick", nowNs: 2n }).currentTimeNs
    ).toBe(beforeGap + 2n);
  });

  it("loops overshoot with modulo arithmetic", () => {
    const loop = {
      startNs: source.startNs + 100n,
      endNs: source.startNs + 200n
    };
    const state = reduce([
      { type: "load", source, nowNs: 0n },
      { type: "loaded", nowNs: 0n },
      { type: "set-loop", range: loop, nowNs: 0n },
      { type: "seek", targetNs: loop.startNs, nowNs: 0n },
      { type: "seeked", generation: 1, nowNs: 0n },
      { type: "play", nowNs: 0n },
      { type: "tick", nowNs: 250n }
    ]);
    expect(state.status).toBe("playing");
    expect(state.currentTimeNs).toBe(loop.startNs + 50n);
  });

  it("buffers only against the master and resumes without counting stalled time", () => {
    let state = reduce([
      { type: "load", source, nowNs: 0n },
      { type: "loaded", nowNs: 0n },
      {
        type: "set-buffer",
        streamId: "video",
        ranges: [{ startNs: source.startNs, endNs: source.startNs + 10n }],
        nowNs: 0n
      },
      { type: "play", nowNs: 0n },
      { type: "tick", nowNs: 20n }
    ]);
    expect(state.status).toBe("loading");
    expect(state.currentTimeNs).toBe(source.startNs + 10n);
    state = playbackReducer(state, {
      type: "set-buffer",
      streamId: "video",
      ranges: [{ startNs: source.startNs, endNs: source.startNs + 100n }],
      nowNs: 1_000n
    });
    expect(state.status).toBe("playing");
    expect(
      playbackReducer(state, { type: "tick", nowNs: 1_005n }).currentTimeNs
    ).toBe(source.startNs + 15n);
  });

  it("normalizes buffers and records exact per-stream drift", () => {
    const state = reduce([
      { type: "load", source, nowNs: 0n },
      {
        type: "set-buffer",
        streamId: "imu",
        ranges: [
          { startNs: 5n, endNs: 8n },
          { startNs: 1n, endNs: 6n }
        ],
        nowNs: 0n
      },
      { type: "set-drift", streamId: "imu", driftNs: -9_007_199_254_740_993n }
    ]);
    expect(state.buffers.imu).toEqual([{ startNs: 1n, endNs: 8n }]);
    expect(state.driftNs.imu).toBe(-9_007_199_254_740_993n);
  });
});

describe("seek generations", () => {
  it("ignores stale success and failure results", () => {
    let state = reduce([
      { type: "load", source, nowNs: 0n },
      { type: "loaded", nowNs: 0n },
      { type: "seek", targetNs: source.startNs + 10n, nowNs: 0n },
      { type: "seek", targetNs: source.startNs + 20n, nowNs: 0n }
    ]);
    const current = state;
    state = playbackReducer(state, {
      type: "seeked",
      generation: 1,
      actualNs: source.startNs + 10n,
      nowNs: 1n
    });
    expect(state).toBe(current);
    expect(
      playbackReducer(state, {
        type: "seek-failed",
        generation: 1,
        message: "late"
      })
    ).toBe(state);
    state = playbackReducer(state, {
      type: "seeked",
      generation: 2,
      nowNs: 2n
    });
    expect(state.currentTimeNs).toBe(source.startNs + 20n);
    expect(state.status).toBe("paused");
  });

  it("survives randomized completion order with only the newest seek winning", () => {
    let seed = 0x1234_5678;
    const random = (): number => {
      seed = (Math.imul(seed, 1_664_525) + 1_013_904_223) >>> 0;
      return seed;
    };
    for (let trial = 0; trial < 100; trial += 1) {
      let state = reduce([
        { type: "load", source, nowNs: 0n },
        { type: "loaded", nowNs: 0n }
      ]);
      const count = 2 + (random() % 20);
      for (let generation = 1; generation <= count; generation += 1)
        state = playbackReducer(state, {
          type: "seek",
          targetNs: source.startNs + BigInt(generation),
          nowNs: 0n
        });
      const order = Array.from({ length: count }, (_, index) => index + 1).sort(
        () => ((random() & 1) === 0 ? -1 : 1)
      );
      for (const generation of order)
        state = playbackReducer(state, {
          type: "seeked",
          generation,
          actualNs: source.startNs + BigInt(generation),
          nowNs: 1n
        });
      expect(state.currentTimeNs).toBe(source.startNs + BigInt(count));
      expect(state.status).toBe("paused");
    }
  });
});
