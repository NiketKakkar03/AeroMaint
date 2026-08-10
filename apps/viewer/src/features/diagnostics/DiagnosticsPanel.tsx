import type { ViewerBenchmarkReport } from "@aeromaint/observability";

export interface DiagnosticsPanelProps {
  readonly report: ViewerBenchmarkReport;
  readonly onExport?: (report: ViewerBenchmarkReport) => void;
}

function milliseconds(value: number | undefined): string {
  return value === undefined ? "unsupported" : `${value.toFixed(1)} ms`;
}

export function DiagnosticsPanel({ report, onExport }: DiagnosticsPanelProps) {
  const { metrics } = report;
  return (
    <section aria-labelledby="viewer-diagnostics-heading">
      <h2 id="viewer-diagnostics-heading">Playback diagnostics</h2>
      <dl>
        <div>
          <dt>First frame</dt>
          <dd>{milliseconds(metrics.timeToFirstFrameMs)}</dd>
        </div>
        <div>
          <dt>Warm seek p50 / p95</dt>
          <dd>
            {milliseconds(metrics.warmSeekP50Ms)} /{" "}
            {milliseconds(metrics.warmSeekP95Ms)}
          </dd>
        </div>
        <div>
          <dt>Dropped / late</dt>
          <dd>
            {metrics.droppedFrames} / {metrics.lateFrames} (
            {(metrics.droppedFrameRate * 100).toFixed(2)}%)
          </dd>
        </div>
        <div>
          <dt>Absolute drift p95 / max</dt>
          <dd>
            {milliseconds(metrics.absoluteDriftP95Ms)} /{" "}
            {milliseconds(metrics.maxAbsoluteDriftMs)}
          </dd>
        </div>
        <div>
          <dt>Buffering</dt>
          <dd>
            {metrics.bufferingCount} events /{" "}
            {milliseconds(metrics.bufferingDurationMs)}
          </dd>
        </div>
        <div>
          <dt>Decoded queue max</dt>
          <dd>{metrics.decodedQueueDepthMax}</dd>
        </div>
        <div>
          <dt>Heap growth</dt>
          <dd>
            {metrics.memoryGrowthBytes === undefined
              ? "unsupported"
              : `${String(metrics.memoryGrowthBytes)} bytes`}
          </dd>
        </div>
        <div>
          <dt>Transferred</dt>
          <dd>{metrics.transferredBytes} bytes</dd>
        </div>
        <div>
          <dt>Long tasks</dt>
          <dd>
            {metrics.longTaskCount} / {milliseconds(metrics.longTaskDurationMs)}
          </dd>
        </div>
      </dl>
      {onExport === undefined ? null : (
        <button
          type="button"
          onClick={() => {
            onExport(report);
          }}
        >
          Export benchmark JSON
        </button>
      )}
    </section>
  );
}
