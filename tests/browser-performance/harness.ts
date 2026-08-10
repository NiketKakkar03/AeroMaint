import {
  PlaybackMetricsCollector,
  observeBrowserResources,
  type BenchmarkIdentity,
  type PerformanceBudgets,
  type ViewerBenchmarkReport
} from "../../packages/observability/src/index.js";

export interface BenchmarkScenario {
  readonly identity: BenchmarkIdentity;
  readonly durationMs: number;
  readonly sampleIntervalMs: number;
  readonly budgets: PerformanceBudgets;
  run(collector: PlaybackMetricsCollector): Promise<void>;
}

/** Browser-runner boundary used by Playwright without coupling metrics to viewer layout. */
export async function runBenchmark(
  scenario: BenchmarkScenario
): Promise<ViewerBenchmarkReport> {
  const startedAt = performance.now();
  const collector = new PlaybackMetricsCollector(startedAt);
  const resources = observeBrowserResources(collector);
  resources.sample();
  const sampleTimer = setInterval(
    () => resources.sample(),
    scenario.sampleIntervalMs
  );
  try {
    await scenario.run(collector);
  } finally {
    clearInterval(sampleTimer);
    resources.sample();
    resources.disconnect();
  }
  return collector.report(
    scenario.identity,
    scenario.durationMs,
    scenario.sampleIntervalMs,
    scenario.budgets
  );
}
