import type { StreamGap } from "@aeromaint/contracts";
import { envelopeForViewport } from "@aeromaint/timeline-renderer";
import { useEffect, useRef } from "react";
import {
  closestSample,
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
  const canvas = useRef<HTMLCanvasElement>(null);
  const duration = endNs - startNs;
  const [min, max] = valueExtent(samples);
  const x = (timeNs: bigint) =>
    duration <= 0n ? 0 : (Number(timeNs - startNs) / Number(duration)) * width;
  const y = (value: number) => height - ((value - min) / (max - min)) * height;
  const selected = closestSample(samples, selectedTimeNs);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;
    const scale = window.devicePixelRatio || 1;
    element.width = width * scale;
    element.height = height * scale;
    context.setTransform(scale, 0, 0, scale, 0, 0);
    context.clearRect(0, 0, width, height);
    context.fillStyle = "rgba(239, 107, 107, 0.12)";
    for (const gap of gaps)
      context.fillRect(
        x(gap.startNs),
        0,
        x(gap.endNs) - x(gap.startNs),
        height
      );
    for (const axis of AXES) {
      const envelopes = envelopeForViewport(
        samples.map((sample) => ({
          timeNs: sample.timeNs,
          value: sample[axis]
        })),
        startNs,
        endNs,
        width
      );
      context.strokeStyle = COLORS[axis];
      context.lineWidth = 1.5;
      context.beginPath();
      for (const envelope of envelopes) {
        const pixelX = x(envelope.startNs);
        context.moveTo(pixelX, y(envelope.min));
        context.lineTo(pixelX, y(envelope.max));
      }
      context.stroke();
    }
    context.strokeStyle = "rgba(255,255,255,0.8)";
    context.beginPath();
    context.moveTo(x(selectedTimeNs), 0);
    context.lineTo(x(selectedTimeNs), height);
    context.stroke();
  }, [endNs, gaps, max, min, samples, selectedTimeNs, startNs]);

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
        <canvas
          ref={canvas}
          className="sensor-plot"
          style={{ width: "100%", height: `${String(height)}px` }}
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
        />
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
