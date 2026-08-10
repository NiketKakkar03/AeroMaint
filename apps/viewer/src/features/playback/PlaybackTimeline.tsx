import type { StreamGap } from "@aeromaint/contracts";
import type { KeyboardEvent } from "react";
import type { TimelineRange } from "./timelineMath";
import {
  formatSessionTime,
  gapAt,
  ratioToTime,
  stepTime,
  timeToRatio
} from "./timelineMath";

export interface TimelineProps {
  readonly range: TimelineRange;
  readonly currentTimeNs: bigint;
  readonly gaps: readonly StreamGap[];
  readonly onSeek: (timeNs: bigint) => void;
  readonly onTogglePlayback: () => void;
  readonly stepNs?: bigint;
}

export function Timeline({
  range,
  currentTimeNs,
  gaps,
  onSeek,
  onTogglePlayback,
  stepNs = 33_333_333n
}: TimelineProps) {
  const durationNs = range.endNs - range.startNs;
  const sliderValue = Math.round(timeToRatio(currentTimeNs, range) * 10_000);
  const activeGap = gapAt(currentTimeNs, gaps);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target instanceof HTMLSelectElement) return;
    if (event.key === " ") {
      event.preventDefault();
      onTogglePlayback();
    } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      onSeek(
        stepTime(
          currentTimeNs,
          event.key === "ArrowLeft" ? -stepNs : stepNs,
          range
        )
      );
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      onSeek(event.key === "Home" ? range.startNs : range.endNs);
    }
  };

  return (
    <div
      className="timeline"
      aria-label="Session timeline. Space plays or pauses; arrow keys step; Home and End seek to bounds."
      onKeyDown={handleKeyDown}
    >
      <div className="timeline-track" aria-hidden="true">
        {gaps.map((gap) => {
          const left = timeToRatio(gap.startNs, range) * 100;
          const width =
            (Number(gap.endNs - gap.startNs) / Number(durationNs)) * 100;
          return (
            <span
              className={`timeline-gap timeline-gap-${gap.reason}`}
              key={`${String(gap.startNs)}-${String(gap.endNs)}-${gap.reason}`}
              style={{ left: `${String(left)}%`, width: `${String(width)}%` }}
              title={`${gap.reason.replaceAll("_", " ")} gap`}
            />
          );
        })}
        <span
          className="timeline-playhead"
          style={{ left: `${String(sliderValue / 100)}%` }}
        />
      </div>
      <input
        type="range"
        min="0"
        max="10000"
        step="1"
        value={sliderValue}
        aria-label="Seek session timeline"
        aria-valuetext={formatSessionTime(currentTimeNs, range.startNs)}
        onChange={(event) => {
          onSeek(
            ratioToTime(Number(event.currentTarget.value) / 10_000, range)
          );
        }}
      />
      <div className="timeline-labels">
        <span>{formatSessionTime(range.startNs, range.startNs)}</span>
        {activeGap ? (
          <strong role="status">
            No data: {activeGap.reason.replaceAll("_", " ")}
          </strong>
        ) : (
          <span>Continuous data</span>
        )}
        <span>{formatSessionTime(range.endNs, range.startNs)}</span>
      </div>
      <ul className="gap-legend" aria-label="Timeline gap legend">
        <li>
          <span className="gap-key gap-key-missing" aria-hidden="true" />
          Missing samples
        </li>
        <li>
          <span className="gap-key gap-key-clock" aria-hidden="true" />
          Clock discontinuity
        </li>
      </ul>
    </div>
  );
}
