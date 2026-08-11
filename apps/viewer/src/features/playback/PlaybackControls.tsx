import type { CaptureSessionManifest } from "@aeromaint/contracts";

interface Props {
  readonly manifest: CaptureSessionManifest;
  readonly playheadNs: bigint;
  readonly playing: boolean;
  readonly playbackRate: number;
  readonly onPlayingChange: (playing: boolean) => void;
  readonly onSeek: (timestampNs: bigint) => void;
  readonly onRateChange: (rate: number) => void;
  readonly loopEnabled: boolean;
  readonly onLoopChange: (enabled: boolean) => void;
  readonly zoom: number;
  readonly onZoomChange: (zoom: number) => void;
}

export function PlaybackControls({
  manifest,
  playheadNs,
  playing,
  playbackRate,
  onPlayingChange,
  onSeek,
  onRateChange,
  loopEnabled,
  onLoopChange,
  zoom,
  onZoomChange
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
      <label>
        Playback rate
        <select
          value={playbackRate}
          onChange={(event) => {
            onRateChange(Number(event.currentTarget.value));
          }}
        >
          {[0.25, 0.5, 1, 2, 4].map((rate) => (
            <option key={rate} value={rate}>
              {rate}×
            </option>
          ))}
        </select>
      </label>
      <label>
        <input
          type="checkbox"
          checked={loopEnabled}
          onChange={(event) => {
            onLoopChange(event.currentTarget.checked);
          }}
        />
        Loop visible window
      </label>
      <button
        type="button"
        aria-label="Zoom out timeline"
        disabled={zoom <= 1}
        onClick={() => {
          onZoomChange(Math.max(1, zoom / 2));
        }}
      >
        Zoom out
      </button>
      <output aria-label="Timeline zoom">{zoom}×</output>
      <button
        type="button"
        aria-label="Zoom in timeline"
        disabled={zoom >= 16}
        onClick={() => {
          onZoomChange(Math.min(16, zoom * 2));
        }}
      >
        Zoom in
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
