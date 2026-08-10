import type { ViewerBenchmarkReport } from "@aeromaint/observability";

export function downloadBenchmarkReport(report: ViewerBenchmarkReport): void {
  const url = URL.createObjectURL(
    new Blob([`${JSON.stringify(report, null, 2)}\n`], {
      type: "application/json"
    })
  );
  const anchor = document.createElement("a");
  anchor.download = `aeromaint-benchmark-${report.identity.runId}.json`;
  anchor.href = url;
  anchor.click();
  URL.revokeObjectURL(url);
}
