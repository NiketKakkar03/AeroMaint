import { useEffect, useMemo, useState } from "react";
import type { Annotation, AnnotationDraft } from "@aeromaint/capture-sdk";
import type { ViewerDataSource } from "../../lib/sdk.js";

export function AnnotationTrack({
  sessionId,
  startNs,
  endNs,
  playheadNs,
  dataSource
}: {
  readonly sessionId: string;
  readonly startNs: bigint;
  readonly endNs: bigint;
  readonly playheadNs: bigint;
  readonly dataSource: ViewerDataSource;
}) {
  const [items, setItems] = useState<readonly Annotation[]>([]);
  const [selected, setSelected] = useState<string>();
  const [kind, setKind] = useState("observation");
  const [shape, setShape] = useState<"point" | "interval">("point");
  const [duration, setDuration] = useState("1");
  const [error, setError] = useState("");
  const reload = () =>
    dataSource.listAnnotations(sessionId).then(setItems, (reason: unknown) => {
      setError(String(reason));
    });
  useEffect(() => {
    void reload();
  }, [sessionId, dataSource]);
  const visible = useMemo(
    () =>
      items.filter((item) => item.endNs >= startNs && item.startNs <= endNs),
    [items, startNs, endNs]
  );
  const selectedItem = items.find(({ id }) => id === selected);
  const submit = async () => {
    setError("");
    const seconds = Number(duration);
    const draft: AnnotationDraft = {
      startNs: playheadNs,
      ...(shape === "interval"
        ? { endNs: playheadNs + BigInt(Math.round(seconds * 1e9)) }
        : {}),
      kind,
      provenance: { source: "viewer", canonical_time: true }
    };
    try {
      if (selectedItem)
        await dataSource.updateAnnotation(sessionId, selectedItem.id, {
          ...draft,
          expectedVersion: selectedItem.version
        });
      else await dataSource.createAnnotation(sessionId, draft);
      setSelected(undefined);
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };
  return (
    <section className="annotation-panel" aria-label="Annotations">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Canonical session time</span>
          <h2>Annotations</h2>
        </div>
        <span>
          {visible.length} visible / {items.length} total
        </span>
      </div>
      <div
        className="annotation-track"
        data-virtualized-track="true"
        aria-label="Virtualized annotation timeline"
      >
        {visible.map((item) => {
          const left =
            (Number(item.startNs - startNs) / Number(endNs - startNs)) * 100;
          const width =
            item.shape === "point"
              ? 0
              : Math.max(
                  0.5,
                  (Number(item.endNs - item.startNs) /
                    Number(endNs - startNs)) *
                    100
                );
          return (
            <button
              type="button"
              key={item.id}
              className={`annotation-mark annotation-${item.shape} annotation-${item.status}`}
              style={{
                left: `${String(left)}%`,
                width: item.shape === "point" ? undefined : `${String(width)}%`
              }}
              aria-label={`${item.kind} ${item.shape}, ${item.status}, version ${String(item.version)}`}
              onClick={() => {
                setSelected(item.id);
                setKind(item.kind);
                setShape(item.shape);
                setDuration(
                  String(Number(item.endNs - item.startNs) / 1e9 || 1)
                );
              }}
            />
          );
        })}
      </div>
      <div className="annotation-editor">
        <label>
          Annotation kind
          <input
            aria-label="Annotation kind"
            value={kind}
            onChange={(event) => {
              setKind(event.currentTarget.value);
            }}
          />
        </label>
        <label>
          Shape
          <select
            aria-label="Annotation shape"
            value={shape}
            onChange={(event) => {
              setShape(event.currentTarget.value as "point" | "interval");
            }}
          >
            <option value="point">Point</option>
            <option value="interval">Interval</option>
          </select>
        </label>
        {shape === "interval" ? (
          <label>
            Duration (seconds)
            <input
              aria-label="Annotation duration"
              type="number"
              min="0.001"
              step="0.1"
              value={duration}
              onChange={(event) => {
                setDuration(event.currentTarget.value);
              }}
            />
          </label>
        ) : null}
        <button type="button" onClick={() => void submit()}>
          {selectedItem ? "Save annotation" : "Add annotation"}
        </button>
        {selectedItem ? (
          <>
            <button
              type="button"
              onClick={() => {
                void dataSource
                  .reviewAnnotation(sessionId, selectedItem.id, {
                    expectedVersion: selectedItem.version,
                    decision: "approved"
                  })
                  .then(async () => {
                    setSelected(undefined);
                    await reload();
                  });
              }}
            >
              Approve
            </button>
            <button
              type="button"
              onClick={() => {
                void dataSource
                  .annotationHistory(sessionId, selectedItem.id)
                  .then((events) => {
                    window.alert(
                      events
                        .map((event) => `${event.action} by ${event.actor}`)
                        .join("\n")
                    );
                  });
              }}
            >
              Audit history
            </button>
          </>
        ) : null}
      </div>
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
