import type { StreamGap } from "@aeromaint/contracts";
import {
  closestSample,
  sampleSegments,
  valueExtent,
  type VectorAxis,
  type VectorSample
} from "./sensorMath";

const AXES: readonly VectorAxis[] = ["x", "y", "z"];
const COLORS: Record<VectorAxis, string> = {
  x: "#6ee7c0",
  y: "#f2b85b",
  z: "#7aa7ff"
};

export interface SensorPlotProps {
  readonly title: string;
  readonly unit: string;
  readonly samples: readonly VectorSample[];
  readonly gaps: readonly StreamGap[];
  readonly startNs: bigint;
  readonly endNs: bigint;
  readonly selectedTimeNs: bigint;
  readonly onSelectTime: (timeNs: bigint) => void;
}

export function SensorPlot({
  title,
  unit,
  samples,
  gaps,
  startNs,
  endNs,
  selectedTimeNs,
  onSelectTime
}: SensorPlotProps) {
  const headingId = `${title.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}-heading`;
  const width = 760;
  const height = 180;
  const duration = endNs - startNs;
  const [min, max] = valueExtent(samples);
  const x = (timeNs: bigint) =>
    duration <= 0n ? 0 : (Number(timeNs - startNs) / Number(duration)) * width;
  const y = (value: number) => height - ((value - min) / (max - min)) * height;
  const selected = closestSample(samples, selectedTimeNs);

  return (
    <section className="sensor-card" aria-labelledby={headingId}>
      <div className="sensor-heading">
        <div>
          <h2 id={headingId}>{title}</h2>
          <span className="sensor-unit">Unit: {unit}</span>
        </div>
        <ul className="sensor-legend" aria-label={`${title} axis legend`}>
          {AXES.map((axis) => (
            <li key={axis}>
              <span style={{ background: COLORS[axis] }} />
              {axis.toUpperCase()}
            </li>
          ))}
        </ul>
      </div>
      <div className="plot-shell">
        <svg
          className="sensor-plot"
          viewBox={`0 0 ${String(width)} ${String(height)}`}
          role="img"
          aria-label={`${title} plot in ${unit}. Select a point to seek playback.`}
          onClick={(event) => {
            const bounds = event.currentTarget.getBoundingClientRect();
            const ratio = Math.max(
              0,
              Math.min(1, (event.clientX - bounds.left) / bounds.width)
            );
            onSelectTime(
              startNs + BigInt(Math.round(Number(duration) * ratio))
            );
          }}
        >
          <title>
            {title} in {unit}
          </title>
          {gaps.map((gap) => (
            <rect
              key={`${gap.startNs}-${gap.endNs}`}
              className="plot-gap"
              x={x(gap.startNs)}
              width={x(gap.endNs) - x(gap.startNs)}
              height={height}
            />
          ))}
          {AXES.flatMap((axis) =>
            sampleSegments(samples, gaps).map((segment, index) => (
              <polyline
                key={`${axis}-${String(index)}`}
                fill="none"
                stroke={COLORS[axis]}
                strokeWidth="2"
                points={segment
                  .map(
                    (sample) =>
                      `${String(x(sample.timeNs))},${String(y(sample[axis]))}`
                  )
                  .join(" ")}
              />
            ))
          )}
          <line
            className="plot-cursor"
            x1={x(selectedTimeNs)}
            x2={x(selectedTimeNs)}
            y1="0"
            y2={height}
          />
        </svg>
        <button
          type="button"
          className="plot-selection"
          aria-label={`Seek ${title} to selected sample`}
          disabled={selected === undefined}
          onClick={() => {
            if (selected) onSelectTime(selected.timeNs);
          }}
        >
          {selected
            ? `Selected — X ${selected.x.toFixed(2)}, Y ${selected.y.toFixed(2)}, Z ${selected.z.toFixed(2)} ${unit}`
            : "No samples available"}
        </button>
      </div>
    </section>
  );
}
