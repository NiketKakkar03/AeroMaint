import { useEffect, useState } from "react";
import type { ModelTrack } from "@aeromaint/contracts";

export function HealthTrack({
  sessionId,
  load
}: {
  readonly sessionId: string;
  readonly load: (
    sessionId: string,
    signal: AbortSignal
  ) => Promise<ModelTrack>;
}) {
  const [track, setTrack] = useState<ModelTrack>();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void load(sessionId, controller.signal).then(setTrack, () => {
      if (!controller.signal.aborted) setFailed(true);
    });
    return () => {
      controller.abort();
    };
  }, [load, sessionId]);
  if (failed)
    return (
      <section className="health-track" role="status">
        <h2>Engine health</h2>
        <p>Prediction evidence is unavailable.</p>
      </section>
    );
  if (!track)
    return (
      <section className="health-track" aria-busy="true">
        <h2>Engine health</h2>
        <p>Loading model track…</p>
      </section>
    );
  const latest = track.points.at(-1);
  return (
    <section className="health-track" aria-label="Engine health model timeline">
      <header>
        <div>
          <span className="eyebrow">Deterministic model track</span>
          <h2>Engine health</h2>
        </div>
        <small>
          {track.versions.model} · data {track.versions.data}
        </small>
      </header>
      {latest?.status === "ok" ? (
        <p>
          <strong>
            {latest.rul?.toFixed(1)} {latest.rulUnit} RUL
          </strong>{" "}
          · uncertainty {latest.interval?.[0].toFixed(1)}–
          {latest.interval?.[1].toFixed(1)} {latest.rulUnit} · horizon{" "}
          {latest.horizon} {latest.horizonUnit}
        </p>
      ) : (
        <p role="status">
          <strong>{latest?.status.replace("_", " ")}</strong> · {latest?.reason}
        </p>
      )}
      <div className="health-overlay" aria-label="RUL and anomaly timeline">
        {track.points.map((point) => (
          <span
            key={point.timestampNs.toString()}
            className={`health-point ${point.anomalySeverity}`}
            title={`${point.status}: ${point.rul === null ? "no prediction" : String(point.rul)} ${point.rulUnit}`}
          />
        ))}
      </div>
      {latest && latest.attribution.length > 0 ? (
        <p className="health-attribution">
          Drivers:{" "}
          {latest.attribution
            .map(
              (item) =>
                `${item.feature} ${item.contribution.toFixed(2)} ${item.unit}`
            )
            .join(" · ")}
        </p>
      ) : null}
      <small>
        Artifact {track.artifactId} · features {track.versions.features} · code{" "}
        {track.versions.code}
      </small>
    </section>
  );
}
