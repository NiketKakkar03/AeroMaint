import { useEffect, useState } from "react";
import { ReviewQueue } from "../review-queue/index.js";
import type { CopilotDataSource, CopilotRun } from "./types.js";

export function CopilotPanel({
  sessionId,
  dataSource
}: {
  readonly sessionId: string;
  readonly dataSource: CopilotDataSource;
}) {
  const [question, setQuestion] = useState("");
  const [runs, setRuns] = useState<readonly CopilotRun[]>([]);
  const [busy, setBusy] = useState(false);
  const refresh = () =>
    dataSource.listCopilotRuns(sessionId).then(setRuns, () => {
      setRuns([]);
    });
  useEffect(() => {
    void refresh();
  }, [dataSource, sessionId]);
  const ask = async () => {
    if (question.trim().length < 2) return;
    setBusy(true);
    try {
      const run = await dataSource.askCopilot(sessionId, question);
      setRuns((current) => [run, ...current]);
      setQuestion("");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="copilot" aria-labelledby="copilot-title">
      <span className="eyebrow">Evidence-backed assistant</span>
      <h2 id="copilot-title">Inspection copilot</h2>
      <p>
        Numerical health is copied only from deterministic public tools. All
        recommendations remain drafts until engineer approval.
      </p>
      <label>
        Ask about this session
        <textarea
          value={question}
          onChange={(event) => {
            setQuestion(event.target.value);
          }}
        />
      </label>
      <button disabled={busy} onClick={() => void ask()}>
        Generate draft
      </button>
      {runs.map((run) => (
        <article
          key={run.id}
          className="copilot-answer"
          data-status={run.status}
        >
          <strong>
            {run.status === "refused" ? "Unable to recommend" : run.status}
          </strong>
          {run.refusal_reason ? (
            <p role="alert">Limitation: {run.refusal_reason}</p>
          ) : null}
          <p>{run.recommendation?.summary}</p>
          {run.recommendation?.claims.map((claim) => (
            <p key={claim.text}>
              {claim.text}{" "}
              {claim.citations.map((citation) => (
                <a
                  key={citation.evidence_id}
                  href={citation.source_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  [{citation.title}, {citation.locator}]
                </a>
              ))}
            </p>
          ))}
        </article>
      ))}
      <ReviewQueue
        runs={runs}
        busy={busy}
        onReview={(run, action) => {
          const revised =
            action === "revised"
              ? (window.prompt(
                  "Revised draft summary",
                  run.recommendation?.summary ?? ""
                ) ?? undefined)
              : undefined;
          if (action === "revised" && revised === undefined) return;
          setBusy(true);
          void dataSource
            .reviewCopilotRun(run.id, action, run.version, revised)
            .then((updated) => {
              setRuns((current) =>
                current.map((item) => (item.id === updated.id ? updated : item))
              );
            })
            .finally(() => {
              setBusy(false);
            });
        }}
      />
    </section>
  );
}
