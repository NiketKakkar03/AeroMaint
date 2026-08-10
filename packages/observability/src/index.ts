export const REPORT_SCHEMA = "aeromaint.viewer-benchmark/v1" as const;

export interface BenchmarkIdentity {
  readonly runId: string;
  readonly startedAt: string;
  readonly browser: string;
  readonly browserVersion: string;
  readonly hardware: string;
  readonly dataset: string;
  readonly datasetVersion: string;
}

export interface PerformanceBudgets {
  readonly warmSeekP95Ms?: number;
  readonly droppedFrameRate?: number;
  readonly absoluteDriftP95Ms?: number;
  readonly memoryGrowthBytes?: number;
}

export interface ResourceObservation {
  readonly atMs: number;
  readonly heapBytes?: number | undefined;
  readonly transferredBytes: number;
  readonly longTaskCount: number;
  readonly longTaskDurationMs: number;
}

export interface ViewerBenchmarkMetrics {
  readonly timeToFirstFrameMs?: number | undefined;
  readonly coldSeekMs?: number | undefined;
  readonly warmSeekP50Ms?: number | undefined;
  readonly warmSeekP95Ms?: number | undefined;
  readonly presentedFrames: number;
  readonly droppedFrames: number;
  readonly lateFrames: number;
  readonly droppedFrameRate: number;
  readonly absoluteDriftP50Ms?: number | undefined;
  readonly absoluteDriftP95Ms?: number | undefined;
  readonly maxAbsoluteDriftMs?: number | undefined;
  readonly bufferingCount: number;
  readonly bufferingDurationMs: number;
  readonly decodedQueueDepthMax: number;
  readonly memoryStartBytes?: number | undefined;
  readonly memoryEndBytes?: number | undefined;
  readonly memoryPeakBytes?: number | undefined;
  readonly memoryGrowthBytes?: number | undefined;
  readonly transferredBytes: number;
  readonly longTaskCount: number;
  readonly longTaskDurationMs: number;
}

export interface ViewerBenchmarkReport {
  readonly schema: typeof REPORT_SCHEMA;
  readonly identity: BenchmarkIdentity;
  readonly window: {
    readonly durationMs: number;
    readonly sampleIntervalMs: number;
  };
  readonly budgets: PerformanceBudgets;
  readonly metrics: ViewerBenchmarkMetrics;
  readonly resources: readonly ResourceObservation[];
  readonly budgetResults: Readonly<
    Record<keyof PerformanceBudgets, boolean | undefined>
  >;
}

export type PlaybackMetricEvent =
  | { readonly type: "first-frame"; readonly atMs: number }
  | {
      readonly type: "seek";
      readonly latencyMs: number;
      readonly warm: boolean;
    }
  | {
      readonly type: "frame";
      readonly driftMs: number;
      readonly dropped?: boolean;
      readonly late?: boolean;
    }
  | { readonly type: "buffering"; readonly durationMs: number }
  | { readonly type: "queue-depth"; readonly depth: number }
  | { readonly type: "resource"; readonly observation: ResourceObservation };

function percentile(
  values: readonly number[],
  fraction: number
): number | undefined {
  if (values.length === 0) return undefined;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.ceil(fraction * sorted.length) - 1];
}

export class PlaybackMetricsCollector {
  readonly #startedAtMs: number;
  readonly #warmSeeks: number[] = [];
  readonly #drift: number[] = [];
  readonly #resources: ResourceObservation[] = [];
  #firstFrameAtMs?: number;
  #coldSeekMs?: number;
  #presentedFrames = 0;
  #droppedFrames = 0;
  #lateFrames = 0;
  #bufferingCount = 0;
  #bufferingDurationMs = 0;
  #queueDepthMax = 0;

  constructor(startedAtMs = 0) {
    this.#startedAtMs = startedAtMs;
  }

  record(event: PlaybackMetricEvent): void {
    switch (event.type) {
      case "first-frame":
        this.#firstFrameAtMs ??= event.atMs;
        break;
      case "seek":
        if (event.warm) this.#warmSeeks.push(event.latencyMs);
        else this.#coldSeekMs ??= event.latencyMs;
        break;
      case "frame":
        if (event.dropped === true) {
          this.#droppedFrames += 1;
        } else {
          this.#presentedFrames += 1;
          this.#drift.push(Math.abs(event.driftMs));
          if (event.late === true) this.#lateFrames += 1;
        }
        break;
      case "buffering":
        this.#bufferingCount += 1;
        this.#bufferingDurationMs += event.durationMs;
        break;
      case "queue-depth":
        this.#queueDepthMax = Math.max(this.#queueDepthMax, event.depth);
        break;
      case "resource":
        this.#resources.push(event.observation);
    }
  }

  report(
    identity: BenchmarkIdentity,
    durationMs: number,
    sampleIntervalMs: number,
    budgets: PerformanceBudgets = {}
  ): ViewerBenchmarkReport {
    const heaps = this.#resources.flatMap(({ heapBytes }) =>
      heapBytes === undefined ? [] : [heapBytes]
    );
    const firstHeap = heaps[0];
    const lastHeap = heaps.at(-1);
    const metrics: ViewerBenchmarkMetrics = {
      timeToFirstFrameMs:
        this.#firstFrameAtMs === undefined
          ? undefined
          : this.#firstFrameAtMs - this.#startedAtMs,
      coldSeekMs: this.#coldSeekMs,
      warmSeekP50Ms: percentile(this.#warmSeeks, 0.5),
      warmSeekP95Ms: percentile(this.#warmSeeks, 0.95),
      presentedFrames: this.#presentedFrames,
      droppedFrames: this.#droppedFrames,
      lateFrames: this.#lateFrames,
      droppedFrameRate:
        this.#presentedFrames + this.#droppedFrames === 0
          ? 0
          : this.#droppedFrames / (this.#presentedFrames + this.#droppedFrames),
      absoluteDriftP50Ms: percentile(this.#drift, 0.5),
      absoluteDriftP95Ms: percentile(this.#drift, 0.95),
      maxAbsoluteDriftMs:
        this.#drift.length === 0 ? undefined : Math.max(...this.#drift),
      bufferingCount: this.#bufferingCount,
      bufferingDurationMs: this.#bufferingDurationMs,
      decodedQueueDepthMax: this.#queueDepthMax,
      memoryStartBytes: firstHeap,
      memoryEndBytes: lastHeap,
      memoryPeakBytes: heaps.length === 0 ? undefined : Math.max(...heaps),
      memoryGrowthBytes:
        firstHeap === undefined || lastHeap === undefined
          ? undefined
          : lastHeap - firstHeap,
      transferredBytes: this.#resources.at(-1)?.transferredBytes ?? 0,
      longTaskCount: this.#resources.at(-1)?.longTaskCount ?? 0,
      longTaskDurationMs: this.#resources.at(-1)?.longTaskDurationMs ?? 0
    };
    return {
      schema: REPORT_SCHEMA,
      identity,
      window: { durationMs, sampleIntervalMs },
      budgets,
      metrics,
      resources: [...this.#resources],
      budgetResults: {
        warmSeekP95Ms: compare(metrics.warmSeekP95Ms, budgets.warmSeekP95Ms),
        droppedFrameRate: compare(
          metrics.droppedFrameRate,
          budgets.droppedFrameRate
        ),
        absoluteDriftP95Ms: compare(
          metrics.absoluteDriftP95Ms,
          budgets.absoluteDriftP95Ms
        ),
        memoryGrowthBytes: compare(
          metrics.memoryGrowthBytes,
          budgets.memoryGrowthBytes
        )
      }
    };
  }
}

function compare(
  value: number | undefined,
  budget: number | undefined
): boolean | undefined {
  return value === undefined || budget === undefined
    ? undefined
    : value <= budget;
}

export interface BrowserResourceMonitor {
  sample(): void;
  disconnect(): void;
}

export function observeBrowserResources(
  collector: PlaybackMetricsCollector,
  now: () => number = performance.now.bind(performance)
): BrowserResourceMonitor {
  let transferredBytes = 0;
  let longTaskCount = 0;
  let longTaskDurationMs = 0;
  const resourceObserver = new PerformanceObserver((list) => {
    for (const entry of list.getEntries())
      transferredBytes += (entry as PerformanceResourceTiming).transferSize;
  });
  const longTaskObserver = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      longTaskCount += 1;
      longTaskDurationMs += entry.duration;
    }
  });
  resourceObserver.observe({ type: "resource", buffered: true });
  if (PerformanceObserver.supportedEntryTypes.includes("longtask"))
    longTaskObserver.observe({ type: "longtask", buffered: true });
  return {
    sample() {
      const memory = (
        performance as Performance & { memory?: { usedJSHeapSize: number } }
      ).memory;
      const common = {
        atMs: now(),
        transferredBytes,
        longTaskCount,
        longTaskDurationMs
      };
      collector.record({
        type: "resource",
        observation:
          memory === undefined
            ? common
            : { ...common, heapBytes: memory.usedJSHeapSize }
      });
    },
    disconnect() {
      resourceObserver.disconnect();
      longTaskObserver.disconnect();
    }
  };
}
