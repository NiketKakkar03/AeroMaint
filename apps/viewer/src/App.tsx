import { useEffect, useMemo, useState } from "react";
import type { CaptureSessionManifest } from "@aeromaint/contracts";
import {
  initialPlaybackState,
  type PlaybackState
} from "@aeromaint/playback-core";
import { StereoMediaSurface } from "./features/media/StereoMediaSurface.js";
import { PlaybackControls } from "./features/playback/PlaybackControls.js";
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
  const playing = playback.status === "playing";
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
        playbackRate={1}
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
  const baseUrl =
    typeof configuredBaseUrl === "string" ? configuredBaseUrl : "/api";
  const dataSource = useMemo(
    () => suppliedDataSource ?? createViewerDataSource(baseUrl),
    [baseUrl, suppliedDataSource]
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
