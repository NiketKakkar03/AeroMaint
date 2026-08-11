import type { StreamGap } from "@aeromaint/contracts";
import type { TimelineEnvelope } from "@aeromaint/timeline-renderer";
import { useEffect, useRef, useState } from "react";
import type {
  ArrowWorkerRequest,
  ArrowWorkerResponse
} from "../../workers/arrow.worker.js";
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
  readonly dataState?: "raw" | "downsampled" | "interpolated" | "model";
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
  dataState = "raw",
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
  const [axisEnvelopes, setAxisEnvelopes] = useState<
    readonly (readonly TimelineEnvelope[])[]
  >([]);

  useEffect(() => {
    const worker = new Worker(
      new URL("../../workers/arrow.worker.ts", import.meta.url),
      { type: "module" }
    );
    const id = crypto.randomUUID();
    const timestampsNs = BigInt64Array.from(
      samples.map((sample) => sample.timeNs)
    );
    const axisValues = AXES.map((axis) =>
      Float64Array.from(samples.map((sample) => sample[axis]))
    ) as [Float64Array, Float64Array, Float64Array];
    worker.onmessage = (event: MessageEvent<ArrowWorkerResponse>) => {
      if (event.data.id === id && event.data.type === "vector-envelope")
        setAxisEnvelopes(event.data.axes);
    };
    worker.postMessage(
      {
        type: "vector-envelope",
        id,
        timestampsNs,
        x: axisValues[0],
        y: axisValues[1],
        z: axisValues[2],
        startNs,
        endNs,
        viewportPixels: width
      } satisfies ArrowWorkerRequest,
      [timestampsNs.buffer, ...axisValues.map((values) => values.buffer)]
    );
    return () => {
      worker.terminate();
    };
  }, [endNs, samples, startNs]);

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
    for (const [axisIndex, axis] of AXES.entries()) {
      const envelopes = axisEnvelopes[axisIndex] ?? [];
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
  }, [axisEnvelopes, endNs, gaps, max, min, selectedTimeNs, startNs]);

  return (
    <section
      className="sensor-card"
      aria-labelledby={headingId}
      data-virtualized-track="true"
      style={{
        contentVisibility: "auto",
        containIntrinsicSize: `auto ${String(height + 80)}px`
      }}
    >
      <div className="sensor-heading">
        <div>
          <h2 id={headingId}>{title}</h2>
          <span className="sensor-unit">Unit: {unit}</span>
          <span className="sensor-unit">Data: {dataState}</span>
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
