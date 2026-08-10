import { useEffect, useRef, useState } from "react";
import type {
  CaptureSessionManifest,
  CaptureStream
} from "@aeromaint/contracts";
import type { ViewerDataSource } from "../../lib/sdk.js";
import { SeekCoordinator, timestampInGap } from "../playback/timeline.js";

interface Props {
  readonly dataSource: ViewerDataSource;
  readonly manifest: CaptureSessionManifest;
  readonly playheadNs: bigint;
  readonly playing: boolean;
  readonly playbackRate: number;
}

function MediaPane(
  props: Props & { readonly stream: CaptureStream | undefined }
) {
  const { dataSource, manifest, stream, playheadNs, playing, playbackRate } =
    props;
  const video = useRef<HTMLVideoElement>(null);
  const coordinator = useRef(new SeekCoordinator());
  const [state, setState] = useState<
    "loading" | "ready" | "buffering" | "error"
  >("loading");
  const gap = stream ? timestampInGap(playheadNs, stream.gaps) : undefined;

  useEffect(() => {
    const element = video.current;
    if (!element || !stream || gap) return;
    const generation = coordinator.current.begin();
    const seconds = Number(playheadNs - manifest.startNs) / 1_000_000_000;
    if (
      Number.isFinite(seconds) &&
      Math.abs(element.currentTime - seconds) > 0.08
    )
      element.currentTime = Math.max(0, seconds);
    element.playbackRate = playbackRate;
    const settle = () => {
      if (coordinator.current.isCurrent(generation)) setState("ready");
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
  return (
    <article className="media-pane">
      <div className="media-heading">
        <div>
          <span>{stream.id}</span>
          <h3>{stream.schemaRef}</h3>
        </div>
        <span className={`media-state ${state}`}>{state}</span>
      </div>
      <div className="video-frame">
        <video
          ref={video}
          aria-label={`${stream.id} media`}
          muted
          playsInline
          preload="metadata"
          onCanPlay={() => {
            setState("ready");
          }}
          onWaiting={() => {
            setState("buffering");
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
        {gap ? (
          <div className="media-overlay" role="status">
            Missing frames · {gap.reason}
          </div>
        ) : null}
        {state === "error" ? (
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
