import { useEffect, useMemo, useRef, useState } from "react";
import type { CaptureSessionManifest } from "@aeromaint/contracts";
import {
  PlaybackMetricsCollector,
  observeBrowserResources,
  type PlaybackMetricEvent,
  type ViewerBenchmarkReport
} from "@aeromaint/observability";
import {
  initialPlaybackState,
  type PlaybackState
} from "@aeromaint/playback-core";
import { StereoMediaSurface } from "./features/media/StereoMediaSurface.js";
import { DiagnosticsPanel } from "./features/diagnostics/DiagnosticsPanel.js";
import { downloadBenchmarkReport } from "./features/diagnostics/reportExport.js";
import { PlaybackControls } from "./features/playback/PlaybackControls.js";
import { Timeline } from "./features/playback/PlaybackTimeline.js";
import { SensorPlot } from "./features/sensors/SensorPlot.js";
import type { VectorSample } from "./features/sensors/sensorMath.js";
import {
  clampTimestamp,
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
  const [playback, setPlayback] = useState<PlaybackState>(() => ({
    ...initialPlaybackState,
    status: "paused",
    currentTimeNs: timestampFromUrl(window.location.search, manifest)
  }));
  const [sensorSamples, setSensorSamples] = useState<readonly VectorSample[]>(
    []
  );
  const [sensorState, setSensorState] = useState<"loading" | "ready" | "error">(
    "loading"
  );
  const metrics = useRef(new PlaybackMetricsCollector(performance.now()));
  const startedAt = useRef(performance.now());
  const [report, setReport] = useState<ViewerBenchmarkReport>();
  const playing = playback.status === "playing";
  const sensorStream = manifest.streams.find(
    (stream) => stream.kind !== "video"
  );
  const gaps = manifest.streams.flatMap((stream) => stream.gaps);
  const recordMetric = (event: PlaybackMetricEvent) => {
    metrics.current.record(event);
  };
  useEffect(() => {
    if (!sensorStream) {
      setSensorSamples([]);
      setSensorState("ready");
      return;
    }
    const controller = new AbortController();
    setSensorState("loading");
    void dataSource
      .loadVectorSamples(
        manifest.sessionId,
        sensorStream.id,
        sensorStream.startNs,
        sensorStream.endNs,
        controller.signal
      )
      .then(
        (samples) => {
          setSensorSamples(samples);
          setSensorState("ready");
        },
        () => {
          if (!controller.signal.aborted) setSensorState("error");
        }
      );
    return () => {
      controller.abort();
    };
  }, [dataSource, manifest.sessionId, sensorStream]);
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
    let previous = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const elapsedNs = BigInt(Math.round((now - previous) * 1_000_000));
      previous = now;
      setPlayback((current) => {
        const next = clampTimestamp(
          current.currentTimeNs + elapsedNs,
          manifest
        );
        return {
          ...current,
          currentTimeNs: next,
          status: next === manifest.endNs ? "ended" : current.status
        };
      });
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
        onPlayingChange={(next) => {
          setPlayback((current) => ({
            ...current,
            status: next ? "playing" : "paused"
          }));
        }}
        onSeek={(currentTimeNs) => {
          setPlayback((current) => ({
            ...current,
            status: "paused",
            currentTimeNs,
            seekGeneration: current.seekGeneration + 1
          }));
        }}
      />
      <Timeline
        range={{ startNs: manifest.startNs, endNs: manifest.endNs }}
        currentTimeNs={playback.currentTimeNs}
        gaps={gaps}
        onTogglePlayback={() => {
          setPlayback((current) => ({
            ...current,
            status: current.status === "playing" ? "paused" : "playing"
          }));
        }}
        onSeek={(currentTimeNs) => {
          setPlayback((current) => ({
            ...current,
            status: "paused",
            currentTimeNs,
            seekGeneration: current.seekGeneration + 1
          }));
        }}
      />
      {sensorStream ? (
        sensorState === "ready" ? (
          <SensorPlot
            title={sensorStream.id}
            unit="stream units"
            samples={sensorSamples}
            gaps={sensorStream.gaps}
            startNs={sensorStream.startNs}
            endNs={sensorStream.endNs}
            selectedTimeNs={playback.currentTimeNs}
            onSelectTime={(currentTimeNs) => {
              setPlayback((current) => ({
                ...current,
                status: "paused",
                currentTimeNs,
                seekGeneration: current.seekGeneration + 1
              }));
            }}
          />
        ) : (
          <p role={sensorState === "error" ? "alert" : "status"}>
            {sensorState === "error"
              ? "Sensor samples could not be loaded."
              : "Loading sensor samples…"}
          </p>
        )
      ) : null}
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
    window.history.pushState(null, "", next);
    setRoute(currentRoute(next));
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
