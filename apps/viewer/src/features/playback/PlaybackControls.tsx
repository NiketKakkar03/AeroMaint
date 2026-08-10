import type { CaptureSessionManifest } from "@aeromaint/contracts";

interface Props {
  readonly manifest: CaptureSessionManifest;
  readonly playheadNs: bigint;
  readonly playing: boolean;
  readonly onPlayingChange: (playing: boolean) => void;
  readonly onSeek: (timestampNs: bigint) => void;
}

export function PlaybackControls({
  manifest,
  playheadNs,
  playing,
  onPlayingChange,
  onSeek
}: Props) {
  const durationNs = manifest.endNs - manifest.startNs;
  const offsetNs = playheadNs - manifest.startNs;
  const maximum = 10_000;
  const value =
    durationNs === 0n ? 0 : Number((offsetNs * BigInt(maximum)) / durationNs);
  return (
    <section className="playback-controls" aria-label="Playback controls">
      <button
        type="button"
        onClick={() => {
          onPlayingChange(!playing);
        }}
      >
        {playing ? "Pause" : "Play"}
      </button>
      <input
        aria-label="Session timeline"
        type="range"
        min={0}
        max={maximum}
        value={value}
        onChange={(event) => {
          onSeek(
            manifest.startNs +
              (durationNs * BigInt(event.currentTarget.value)) / BigInt(maximum)
          );
        }}
      />
      <output>{(Number(offsetNs) / 1_000_000_000).toFixed(3)} s</output>
    </section>
  );
}
