import { useEffect, useRef, useState } from "react";
import type {
  CaptureSessionManifest,
  CaptureStream
} from "@aeromaint/contracts";
import type { PlaybackMetricEvent } from "@aeromaint/observability";
import { selectDecoderCapability } from "@aeromaint/playback-core";
import type { ViewerDataSource } from "../../lib/sdk.js";
import { SeekCoordinator, timestampInGap } from "../playback/timeline.js";

interface Props {
  readonly dataSource: ViewerDataSource;
  readonly manifest: CaptureSessionManifest;
  readonly playheadNs: bigint;
  readonly playing: boolean;
  readonly playbackRate: number;
  readonly onMetricEvent?: (event: PlaybackMetricEvent) => void;
}

function MediaPane(
  props: Props & { readonly stream: CaptureStream | undefined }
) {
  const { dataSource, manifest, stream, playheadNs, playing, playbackRate } =
    props;
  const video = useRef<HTMLVideoElement>(null);
  const coordinator = useRef(new SeekCoordinator());
  const seekStartedAt = useRef<number | null>(null);
  const bufferingStartedAt = useRef<number | null>(null);
  const [state, setState] = useState<
    "loading" | "ready" | "buffering" | "error"
  >("loading");
  const [mediaPath, setMediaPath] = useState("HTML media fallback");
  const gap = stream ? timestampInGap(playheadNs, stream.gaps) : undefined;

  useEffect(() => {
    const codec = stream?.schemaRef.match(
      /(?:avc1|hvc1|hev1|vp09|av01)[^, ]*/
    )?.[0];
    if (!codec) {
      setMediaPath("HTML media fallback");
      return;
    }
    let active = true;
    void selectDecoderCapability(codec).then((capability) => {
      if (active)
        setMediaPath(
          capability.mode === "webcodecs"
            ? "WebCodecs available · HTML fallback active"
            : "HTML media fallback"
        );
    });
    return () => {
      active = false;
    };
  }, [stream]);

  useEffect(() => {
    const element = video.current;
    if (!element || !stream || gap) return;
    const generation = coordinator.current.begin();
    seekStartedAt.current = performance.now();
    const seconds = Number(playheadNs - manifest.startNs) / 1_000_000_000;
    if (
      Number.isFinite(seconds) &&
      Math.abs(element.currentTime - seconds) > 0.08
    )
      element.currentTime = Math.max(0, seconds);
    element.playbackRate = playbackRate;
    const settle = () => {
      if (coordinator.current.isCurrent(generation)) {
        setState("ready");
        if (seekStartedAt.current !== null) {
          props.onMetricEvent?.({
            type: "seek",
            latencyMs: performance.now() - seekStartedAt.current,
            warm: element.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA
          });
          seekStartedAt.current = null;
        }
      }
    };
    element.addEventListener("seeked", settle, { once: true });
    if (playing)
      void element.play().catch(() => {
        setState("error");
      });
    else element.pause();
    return () => {
      element.removeEventListener("seeked", settle);
    };
  }, [gap, manifest.startNs, playbackRate, playheadNs, playing, stream]);

  if (!stream)
    return (
      <article className="media-pane empty">
        <h3>Camera unavailable</h3>
        <p>No video stream was published.</p>
      </article>
    );
  const sources = dataSource.mediaSources(manifest.sessionId, stream, manifest);
  const synthetic = sources.find((source) => source.synthetic)?.synthetic;
  const unsupported = sources.some(
    (source) => source.compatibility === "unsupported"
  );
  return (
    <article className="media-pane">
      <div className="media-heading">
        <div>
          <span>{stream.id}</span>
          <h3>{stream.schemaRef}</h3>
        </div>
        <span
          className={`media-state ${unsupported ? "error" : synthetic ? "ready" : state}`}
        >
          {unsupported ? "unsupported" : synthetic ? "ready" : state}
        </span>
        <span className="media-path">{mediaPath}</span>
      </div>
      <div className="video-frame">
        {synthetic ? (
          <div
            className="synthetic-media"
            data-testid={`${stream.id}-fixture-media`}
            style={{ "--fixture-hue": synthetic.hue } as React.CSSProperties}
            aria-label={`${stream.id} media`}
          >
            <strong>{synthetic.label}</strong>
            <span>
              {(Number(playheadNs - manifest.startNs) / 1_000_000_000).toFixed(
                3
              )}{" "}
              s
            </span>
          </div>
        ) : (
          <video
            ref={video}
            aria-label={`${stream.id} media`}
            muted
            playsInline
            preload="metadata"
            onCanPlay={() => {
              setState("ready");
              props.onMetricEvent?.({
                type: "first-frame",
                atMs: performance.now()
              });
              if (bufferingStartedAt.current !== null) {
                props.onMetricEvent?.({
                  type: "buffering",
                  durationMs: performance.now() - bufferingStartedAt.current
                });
                bufferingStartedAt.current = null;
              }
            }}
            onWaiting={() => {
              setState("buffering");
              bufferingStartedAt.current ??= performance.now();
            }}
            onTimeUpdate={(event) => {
              const mediaTimeNs =
                manifest.startNs +
                BigInt(
                  Math.round(event.currentTarget.currentTime * 1_000_000_000)
                );
              props.onMetricEvent?.({
                type: "frame",
                driftMs: Number(mediaTimeNs - playheadNs) / 1_000_000,
                late: Math.abs(Number(mediaTimeNs - playheadNs)) > 80_000_000
              });
            }}
            onError={() => {
              setState("error");
            }}
          >
            {sources.map((source) => (
              <source key={source.src} src={source.src} type={source.type} />
            ))}
            This browser cannot play the published media.
          </video>
        )}
        {gap ? (
          <div className="media-overlay" role="status">
            Missing frames · {gap.reason}
          </div>
        ) : null}
        {state === "error" || unsupported ? (
          <div className="media-overlay error" role="alert">
            Unsupported codec or media unavailable
          </div>
        ) : null}
      </div>
      <dl>
        <div>
          <dt>Samples</dt>
          <dd>{stream.sampleCount.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Clock</dt>
          <dd>{stream.clockId}</dd>
        </div>
        <div>
          <dt>Gaps</dt>
          <dd>{stream.gaps.length}</dd>
        </div>
      </dl>
    </article>
  );
}

export function StereoMediaSurface(props: Props) {
  const streams = props.manifest.streams.filter(
    (stream) => stream.kind === "video"
  );
  return (
    <section className="stereo-grid" aria-label="Synchronized stereo media">
      <MediaPane {...props} stream={streams[0]} />
      <MediaPane {...props} stream={streams[1]} />
    </section>
  );
}
