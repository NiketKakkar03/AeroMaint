import type { SessionSummary } from "../../lib/sdk.js";

interface Props {
  readonly sessions: readonly SessionSummary[];
  readonly onOpen: (sessionId: string) => void;
}

export function SessionLibrary({ sessions, onOpen }: Props) {
  if (sessions.length === 0)
    return (
      <section className="empty-state">
        <h2>No capture sessions</h2>
        <p>Import a session to begin inspection.</p>
      </section>
    );
  return (
    <section aria-labelledby="sessions-heading">
      <div className="section-heading">
        <p>Library</p>
        <h2 id="sessions-heading">Capture sessions</h2>
      </div>
      <div className="session-list">
        {sessions.map(({ id, manifest, processingStatus }) => {
          const duration = manifest
            ? Number(manifest.endNs - manifest.startNs) / 1_000_000_000
            : undefined;
          return (
            <button
              className="session-card"
              type="button"
              key={id}
              onClick={() => {
                onOpen(id);
              }}
              disabled={!manifest}
            >
              <span className={`processing ${processingStatus}`}>
                {processingStatus}
              </span>
              <h3>{manifest?.displayName ?? id}</h3>
              <dl>
                <div>
                  <dt>Source</dt>
                  <dd>{manifest?.provenance.sourceType ?? "Unavailable"}</dd>
                </div>
                <div>
                  <dt>Duration</dt>
                  <dd>
                    {duration === undefined ? "—" : `${duration.toFixed(2)} s`}
                  </dd>
                </div>
                <div>
                  <dt>Streams</dt>
                  <dd>{manifest?.streams.length ?? "—"}</dd>
                </div>
                <div>
                  <dt>Schema</dt>
                  <dd>{manifest?.schemaVersion ?? "—"}</dd>
                </div>
              </dl>
            </button>
          );
        })}
      </div>
    </section>
  );
}
