import { useEffect, useRef, useState } from "react";
import type {
  CaptureSessionManifest,
  CaptureStream
} from "@aeromaint/contracts";
import type { PlaybackMetricEvent } from "@aeromaint/observability";
import {
  BoundedFrameQueue,
  selectDecoderCapability
} from "@aeromaint/playback-core";
import type {
  DecoderRequest,
  DecoderResponse
} from "../../workers/media-decoder.worker.js";
import type { ViewerDataSource } from "../../lib/sdk.js";
import { SeekCoordinator, timestampInGap } from "../playback/timeline.js";

const mediaBuffers = new Map<string, Promise<ArrayBuffer>>();

function loadMediaBuffer(src: string): Promise<ArrayBuffer> {
  let pending = mediaBuffers.get(src);
  if (!pending) {
    pending = fetch(src)
      .then((response) => {
        if (!response.ok)
          throw new Error(`Media request failed (${String(response.status)})`);
        return response.arrayBuffer();
      })
      .catch((error: unknown) => {
        mediaBuffers.delete(src);
        throw error;
      });
    mediaBuffers.set(src, pending);
  }
  return pending.then((buffer) => buffer.slice(0));
}

interface Props {
  readonly dataSource: ViewerDataSource;
  readonly manifest: CaptureSessionManifest;
  readonly playheadNs: bigint;
  readonly playing: boolean;
  readonly playbackRate: number;
  readonly onMetricEvent?: (event: PlaybackMetricEvent) => void;
}

function WorkerVideo({
  src,
  playheadUs,
  onError,
  onReady
}: {
  readonly src: string;
  readonly playheadUs: number;
  readonly onError: () => void;
  readonly onReady: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const generation = useRef(0);
  const queue = useRef(
    new BoundedFrameQueue<{
      timestampUs: number;
      frame: VideoFrame;
      close(): void;
    }>(12)
  );
  const callbacks = useRef({ onError, onReady });
  callbacks.current = { onError, onReady };
  const targetUs = useRef(playheadUs);
  targetUs.current = playheadUs;
  const seekStartUs = Math.floor(playheadUs / 1_000_000) * 1_000_000;

  useEffect(() => {
    const current = ++generation.current;
    const worker = new Worker(
      new URL("../../workers/media-decoder.worker.ts", import.meta.url),
      { type: "module" }
    );
    const controller = new AbortController();
    worker.onmessage = (event: MessageEvent<DecoderResponse>) => {
      if (event.data.generation !== current) {
        if (event.data.type === "frame") event.data.frame.close();
        return;
      }
      if (event.data.type === "error") callbacks.current.onError();
      if (event.data.type === "ready") callbacks.current.onReady();
      if (event.data.type === "frame") {
        const decodedFrame = event.data.frame;
        queue.current.push({
          timestampUs: decodedFrame.timestamp,
          frame: decodedFrame,
          close() {
            decodedFrame.close();
          }
        });
        const frame = queue.current.takeAtOrBefore(targetUs.current);
        const context = canvas.current?.getContext("2d");
        const element = canvas.current;
        if (frame && context && element) {
          element.width = frame.frame.displayWidth;
          element.height = frame.frame.displayHeight;
          context.drawImage(frame.frame, 0, 0);
          frame.close();
        }
      }
    };
    void loadMediaBuffer(src)
      .then((container) => {
        if (controller.signal.aborted) return;
        worker.postMessage(
          {
            type: "demux",
            generation: current,
            container,
            startUs: seekStartUs
          } satisfies DecoderRequest,
          [container]
        );
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          callbacks.current.onError();
      });
    return () => {
      controller.abort();
      generation.current += 1;
      queue.current.clear();
      worker.postMessage({ type: "close" } satisfies DecoderRequest);
      worker.terminate();
    };
  }, [seekStartUs, src]);

  return <canvas ref={canvas} aria-label="WebCodecs decoded media" />;
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
  const gap = stream
    ? (timestampInGap(playheadNs, stream.gaps) ??
      stream.gaps.find((candidate) => candidate.endNs === playheadNs))
    : undefined;
  const sources = stream
    ? dataSource.mediaSources(manifest.sessionId, stream, manifest)
    : [];
  const workerSource = sources.find((source) => source.type === "video/x-ivf");
  const declaredCodec = workerSource
    ? "vp8"
    : stream?.schemaRef.match(/(?:avc1|hvc1|hev1|vp09|av01)[^, ]*/)?.[0];

  useEffect(() => {
    if (!declaredCodec) {
      setMediaPath("HTML media fallback");
      return;
    }
    let active = true;
    void selectDecoderCapability(declaredCodec).then((capability) => {
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
  }, [declaredCodec]);

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
        ) : workerSource && mediaPath.startsWith("WebCodecs") ? (
          <WorkerVideo
            src={workerSource.src}
            playheadUs={Number(playheadNs - manifest.startNs) / 1_000}
            onReady={() => {
              setState("ready");
              setMediaPath("WebCodecs worker · IVF demux");
            }}
            onError={() => {
              setState("error");
            }}
          />
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
