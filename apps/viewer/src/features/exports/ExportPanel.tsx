import { useEffect, useState } from "react";
import type { ExportJob } from "@aeromaint/capture-sdk";
import type { ViewerDataSource } from "../../lib/sdk.js";

export function ExportPanel({
  sessionId,
  startNs,
  endNs,
  dataSource
}: {
  readonly sessionId: string;
  readonly startNs: bigint;
  readonly endNs: bigint;
  readonly dataSource: ViewerDataSource;
}) {
  const [job, setJob] = useState<ExportJob>();
  const [format, setFormat] = useState<"arrow" | "json">("arrow");
  const [error, setError] = useState("");
  useEffect(() => {
    if (!job || !["pending", "running"].includes(job.status)) return;
    const timer = window.setInterval(() => {
      void dataSource.getExport(job.id).then(setJob, (reason: unknown) => {
        setError(String(reason));
      });
    }, 500);
    return () => {
      window.clearInterval(timer);
    };
  }, [dataSource, job]);
  return (
    <section className="export-panel" aria-label="Export synchronized range">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Half-open [start, end)</span>
          <h2>Export synchronized range</h2>
        </div>
      </div>
      <label>
        Sensor format
        <select
          aria-label="Sensor export format"
          value={format}
          onChange={(event) => {
            setFormat(event.currentTarget.value as "arrow" | "json");
          }}
        >
          <option value="arrow">Arrow</option>
          <option value="json">JSON</option>
        </select>
      </label>
      <button
        type="button"
        onClick={() => {
          setError("");
          void dataSource
            .createExport(sessionId, startNs, endNs, format)
            .then(setJob, (reason: unknown) => {
              setError(String(reason));
            });
        }}
      >
        Create export
      </button>
      {job ? (
        <p role="status">
          Export {job.status} · {String(Math.round(job.progress * 100))}%
        </p>
      ) : null}
      {job && ["pending", "running"].includes(job.status) ? (
        <button
          type="button"
          onClick={() => void dataSource.cancelExport(job.id).then(setJob)}
        >
          Cancel export
        </button>
      ) : null}
      {job?.manifestUrl ? (
        <a href={dataSource.exportFileUrl(job.manifestUrl)} download>
          Download manifest
        </a>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
