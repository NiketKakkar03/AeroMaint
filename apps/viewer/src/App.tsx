import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { CaptureSessionManifest } from "@aeromaint/contracts";
import {
  PlaybackMetricsCollector,
  observeBrowserResources,
  type PlaybackMetricEvent,
  type ViewerBenchmarkReport
} from "@aeromaint/observability";
import {
  initialPlaybackState,
  playbackReducer,
  type PlaybackState
} from "@aeromaint/playback-core";
import { StereoMediaSurface } from "./features/media/StereoMediaSurface.js";
import { DiagnosticsPanel } from "./features/diagnostics/DiagnosticsPanel.js";
import { downloadBenchmarkReport } from "./features/diagnostics/reportExport.js";
import { PlaybackControls } from "./features/playback/PlaybackControls.js";
import { Timeline } from "./features/playback/PlaybackTimeline.js";
import { SensorPlot } from "./features/sensors/SensorPlot.js";
import { AnnotationTrack } from "./features/annotations/index.js";
import type { VectorSample } from "./features/sensors/sensorMath.js";
import { sensorWindow } from "./features/sensors/sensorWindow.js";
import {
  timestampFromUrl,
  urlWithTimestamp
} from "./features/playback/timeline.js";
import {
  createViewerDataSource,
  type SessionSummary,
  type ViewerDataSource
} from "./lib/sdk.js";
import { SessionLibrary } from "./routes/sessions/SessionLibrary.js";

type Route =
  | { readonly kind: "library" }
  | { readonly kind: "session"; readonly sessionId: string };

function currentRoute(pathname = window.location.pathname): Route {
  const match = /^\/sessions\/([^/]+)$/.exec(pathname);
  return match?.[1]
    ? { kind: "session", sessionId: decodeURIComponent(match[1]) }
    : { kind: "library" };
}

function SessionViewer({
  manifest,
  dataSource,
  onBack
}: {
  readonly manifest: CaptureSessionManifest;
  readonly dataSource: ViewerDataSource;
  readonly onBack: () => void;
}) {
  const nowNs = () => BigInt(Math.round(performance.now() * 1_000_000));
  const [playback, dispatchPlayback] = useReducer(
    playbackReducer,
    undefined,
    (): PlaybackState => {
      const source = {
        startNs: manifest.startNs,
        endNs: manifest.endNs,
        streams: manifest.streams.map(({ id, gaps }) => ({ id, gaps })),
        masterStreamId:
          manifest.streams.find((stream) => stream.kind === "video")?.id ??
          manifest.streams[0]?.id ??
          ""
      };
      const clock = nowNs();
      let state = playbackReducer(initialPlaybackState, {
        type: "load",
        source,
        nowNs: clock
      });
      state = playbackReducer(state, { type: "loaded", nowNs: clock });
      const selected = timestampFromUrl(window.location.search, manifest);
      if (selected !== manifest.startNs) {
        state = playbackReducer(state, {
          type: "seek",
          targetNs: selected,
          nowNs: clock
        });
        state = playbackReducer(state, {
          type: "seeked",
          generation: state.seekGeneration,
          actualNs: selected,
          nowNs: clock
        });
      }
      return state;
    }
  );
  const [sensorTracks, setSensorTracks] = useState<
    Readonly<
      Record<
        string,
        {
          readonly state: "loading" | "ready" | "error";
          readonly samples: readonly VectorSample[];
        }
      >
    >
  >({});
  const [zoom, setZoom] = useState(1);
  const metrics = useRef(new PlaybackMetricsCollector(performance.now()));
  const startedAt = useRef(performance.now());
  const [report, setReport] = useState<ViewerBenchmarkReport>();
  const playing = playback.status === "playing";
  const sensorStreams = useMemo(
    () =>
      manifest.streams.filter(
        (stream) => stream.kind === "imu" || stream.kind === "pose"
      ),
    [manifest.streams]
  );
  const visibleWindow = sensorWindow(
    manifest.startNs,
    manifest.endNs,
    playback.currentTimeNs,
    zoom
  );
  const gaps = manifest.streams.flatMap((stream) => stream.gaps);
  const recordMetric = (event: PlaybackMetricEvent) => {
    metrics.current.record(event);
  };
  useEffect(() => {
    if (sensorStreams.length === 0) return;
    const controller = new AbortController();
    setSensorTracks((current) =>
      Object.fromEntries(
        sensorStreams.map((stream) => [
          stream.id,
          { state: "loading", samples: current[stream.id]?.samples ?? [] }
        ])
      )
    );
    for (const stream of sensorStreams)
      void dataSource
        .loadVectorSamples(
          manifest.sessionId,
          stream.id,
          visibleWindow.requestStartNs,
          visibleWindow.requestEndNs,
          controller.signal
        )
        .then(
          (samples) => {
            setSensorTracks((current) => ({
              ...current,
              [stream.id]: { state: "ready", samples }
            }));
          },
          () => {
            if (!controller.signal.aborted)
              setSensorTracks((current) => ({
                ...current,
                [stream.id]: { state: "error", samples: [] }
              }));
          }
        );
    return () => {
      controller.abort();
    };
  }, [
    dataSource,
    manifest.sessionId,
    sensorStreams,
    visibleWindow.requestEndNs,
    visibleWindow.requestStartNs
  ]);
  useEffect(() => {
    const monitor = observeBrowserResources(metrics.current);
    const update = () => {
      monitor.sample();
      setReport(
        metrics.current.report(
          {
            runId: `${manifest.sessionId}-${String(Math.round(startedAt.current))}`,
            startedAt: new Date().toISOString(),
            browser: navigator.userAgent,
            browserVersion: navigator.userAgent,
            hardware: `${String(navigator.hardwareConcurrency)} logical cores`,
            dataset: manifest.displayName,
            datasetVersion: manifest.schemaVersion
          },
          performance.now() - startedAt.current,
          1_000,
          { warmSeekP95Ms: 250, absoluteDriftP95Ms: 80 }
        )
      );
    };
    update();
    const timer = window.setInterval(update, 1_000);
    return () => {
      window.clearInterval(timer);
      monitor.disconnect();
    };
  }, [manifest]);
  useEffect(() => {
    window.history.replaceState(
      null,
      "",
      urlWithTimestamp(new URL(window.location.href), playback.currentTimeNs)
    );
  }, [playback.currentTimeNs]);
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      dispatchPlayback({ type: "tick", nowNs: nowNs() });
    }, 50);
    return () => {
      window.clearInterval(timer);
    };
  }, [manifest, playing]);
  return (
    <main>
      <header className="viewer-header">
        <button type="button" className="back" onClick={onBack}>
          ← Sessions
        </button>
        <div>
          <span className="eyebrow">Synchronized inspection</span>
          <h1>{manifest.displayName}</h1>
          <p className="intro">
            {manifest.provenance.sourceType} · {manifest.streams.length} streams
            · schema {manifest.schemaVersion}
          </p>
        </div>
      </header>
      <StereoMediaSurface
        dataSource={dataSource}
        manifest={manifest}
        playheadNs={playback.currentTimeNs}
        playing={playing}
        playbackRate={playback.playbackRate}
        onMetricEvent={recordMetric}
      />
      <PlaybackControls
        manifest={manifest}
        playheadNs={playback.currentTimeNs}
        playing={playing}
        playbackRate={playback.playbackRate}
        onPlayingChange={(next) => {
          dispatchPlayback({ type: next ? "play" : "pause", nowNs: nowNs() });
        }}
        onSeek={(currentTimeNs) => {
          dispatchPlayback({
            type: "seek",
            targetNs: currentTimeNs,
            nowNs: nowNs()
          });
          dispatchPlayback({
            type: "seeked",
            generation: playback.seekGeneration + 1,
            actualNs: currentTimeNs,
            nowNs: nowNs()
          });
        }}
        onRateChange={(rate) => {
          dispatchPlayback({ type: "set-rate", rate, nowNs: nowNs() });
        }}
        loopEnabled={playback.loopRange !== null}
        onLoopChange={(enabled) => {
          dispatchPlayback({
            type: "set-loop",
            range: enabled
              ? {
                  startNs: visibleWindow.visibleStartNs,
                  endNs: visibleWindow.visibleEndNs
                }
              : null,
            nowNs: nowNs()
          });
        }}
        zoom={zoom}
        onZoomChange={setZoom}
      />
      <Timeline
        range={{
          startNs: visibleWindow.visibleStartNs,
          endNs: visibleWindow.visibleEndNs
        }}
        currentTimeNs={playback.currentTimeNs}
        gaps={gaps}
        onTogglePlayback={() => {
          dispatchPlayback({
            type: playing ? "pause" : "play",
            nowNs: nowNs()
          });
        }}
        onSeek={(currentTimeNs) => {
          dispatchPlayback({
            type: "seek",
            targetNs: currentTimeNs,
            nowNs: nowNs()
          });
          dispatchPlayback({
            type: "seeked",
            generation: playback.seekGeneration + 1,
            actualNs: currentTimeNs,
            nowNs: nowNs()
          });
        }}
      />
      <AnnotationTrack
        sessionId={manifest.sessionId}
        startNs={visibleWindow.visibleStartNs}
        endNs={visibleWindow.visibleEndNs}
        playheadNs={playback.currentTimeNs}
        dataSource={dataSource}
      />
      {sensorStreams.map((stream) => {
        const track = sensorTracks[stream.id];
        return track?.state === "ready" ? (
          <SensorPlot
            key={stream.id}
            title={stream.id}
            unit={stream.kind === "imu" ? "m/s²" : "m / degrees"}
            dataState="raw"
            samples={track.samples}
            gaps={stream.gaps}
            startNs={visibleWindow.visibleStartNs}
            endNs={visibleWindow.visibleEndNs}
            selectedTimeNs={playback.currentTimeNs}
            onSelectTime={(currentTimeNs) => {
              dispatchPlayback({
                type: "seek",
                targetNs: currentTimeNs,
                nowNs: nowNs()
              });
              dispatchPlayback({
                type: "seeked",
                generation: playback.seekGeneration + 1,
                actualNs: currentTimeNs,
                nowNs: nowNs()
              });
            }}
          />
        ) : (
          <p
            key={stream.id}
            role={track?.state === "error" ? "alert" : "status"}
          >
            {track?.state === "error"
              ? `${stream.id} samples could not be loaded.`
              : `Loading ${stream.id} samples…`}
          </p>
        );
      })}
      {report ? (
        <DiagnosticsPanel report={report} onExport={downloadBenchmarkReport} />
      ) : null}
      <aside>
        Educational decision-support prototype. Missing evidence and
        compatibility failures are shown explicitly.
      </aside>
    </main>
  );
}

export function App({
  dataSource: suppliedDataSource
}: {
  readonly dataSource?: ViewerDataSource;
}) {
  const configuredBaseUrl: unknown = import.meta.env.VITE_API_BASE_URL;
  const baseUrl = new URL(
    typeof configuredBaseUrl === "string" ? configuredBaseUrl : "/api",
    window.location.origin
  ).toString();
  const configuredToken: unknown = import.meta.env.VITE_API_TOKEN;
  const token =
    typeof configuredToken === "string" ? configuredToken : undefined;
  const dataSource = useMemo(
    () =>
      suppliedDataSource ??
      createViewerDataSource(baseUrl, globalThis.fetch.bind(globalThis), token),
    [baseUrl, suppliedDataSource, token]
  );
  const [route, setRoute] = useState(currentRoute);
  const [sessions, setSessions] = useState<readonly SessionSummary[]>([]);
  const [manifest, setManifest] = useState<CaptureSessionManifest>();
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  useEffect(() => {
    const onPopState = () => {
      setRoute(currentRoute());
    };
    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("popstate", onPopState);
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    setError("");
    setManifest(undefined);
    const request =
      route.kind === "library"
        ? dataSource.listSessions(controller.signal)
        : dataSource.getSessionManifest(route.sessionId, controller.signal);
    void request.then(
      (result) => {
        if (route.kind === "library")
          setSessions(result as readonly SessionSummary[]);
        else setManifest(result as CaptureSessionManifest);
        setState("ready");
      },
      (reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : String(reason));
        setState("error");
      }
    );
    return () => {
      controller.abort();
    };
  }, [dataSource, route]);
  const navigate = (next: string) => {
    const target = new URL(next, window.location.origin);
    if (new URLSearchParams(window.location.search).has("fixture"))
      target.searchParams.set("fixture", "1");
    window.history.pushState(null, "", `${target.pathname}${target.search}`);
    setRoute(currentRoute(target.pathname));
  };
  if (state === "loading")
    return (
      <main className="center-state" aria-busy="true">
        <span className="eyebrow">Loading</span>
        <h1>Opening capture data…</h1>
      </main>
    );
  if (state === "error")
    return (
      <main className="center-state" role="alert">
        <span className="eyebrow">Unable to load</span>
        <h1>Session data unavailable</h1>
        <p>{error}</p>
        <button
          type="button"
          onClick={() => {
            navigate("/sessions");
          }}
        >
          Return to library
        </button>
      </main>
    );
  if (route.kind === "session" && manifest)
    return (
      <SessionViewer
        manifest={manifest}
        dataSource={dataSource}
        onBack={() => {
          navigate("/sessions");
        }}
      />
    );
  return (
    <main>
      <header>
        <span className="eyebrow">AeroMaint Studio / Session library</span>
        <h1>Engineering data, synchronized.</h1>
        <p className="intro">
          Choose a capture session to inspect every published stream against one
          authoritative timeline.
        </p>
      </header>
      <SessionLibrary
        sessions={sessions}
        onOpen={(id) => {
          navigate(`/sessions/${encodeURIComponent(id)}`);
        }}
      />
      <aside>
        Educational decision-support prototype. Not approved for vehicle control
        or aircraft maintenance.
      </aside>
    </main>
  );
}
