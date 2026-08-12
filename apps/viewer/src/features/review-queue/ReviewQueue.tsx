import type { CopilotRun } from "../copilot/types.js";

export function ReviewQueue({
  runs,
  busy,
  onReview
}: {
  readonly runs: readonly CopilotRun[];
  readonly busy: boolean;
  readonly onReview: (
    run: CopilotRun,
    action: "approved" | "rejected" | "revised"
  ) => void;
}) {
  const drafts = runs.filter(
    (run) => run.status === "draft" || run.status === "revised"
  );
  return (
    <section aria-labelledby="review-queue-title">
      <span className="eyebrow">Human gate</span>
      <h2 id="review-queue-title">Recommendation review queue</h2>
      {drafts.length === 0 ? <p>No drafts awaiting review.</p> : null}
      {drafts.map((run) => (
        <article className="review-card" key={run.id}>
          <strong>Draft only</strong>
          <p>{run.recommendation?.summary}</p>
          <div className="review-actions">
            <button
              disabled={busy}
              onClick={() => {
                onReview(run, "approved");
              }}
            >
              Approve recommendation
            </button>
            <button
              disabled={busy}
              onClick={() => {
                onReview(run, "rejected");
              }}
            >
              Reject
            </button>
            <button
              disabled={busy}
              onClick={() => {
                onReview(run, "revised");
              }}
            >
              Revise
            </button>
          </div>
        </article>
      ))}
    </section>
  );
}
