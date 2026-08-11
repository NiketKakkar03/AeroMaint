import { useEffect, useMemo, useRef, useState } from "react";
import {
  CaptureClient,
  CaptureSdkError,
  type CaptureSessionManifest,
  type ExportJob,
  type SessionSummary
} from "@aeromaint/capture-sdk";

export interface MinimalViewerProps {
  readonly baseUrl: string;
  readonly token?: string;
}

interface ImuRow {
  readonly timestamp_ns?: bigint;
  readonly values?: Readonly<Record<string, unknown>>;
}

export function MinimalViewer({ baseUrl, token }: MinimalViewerProps) {
  const client = useMemo(
    () => new CaptureClient({ baseUrl, ...(token === undefined ? {} : { auth: token }) }),
    [baseUrl, token]
  );
  const video = useRef<HTMLVideoElement>(null);
  const [sessions, setSessions] = useState<readonly SessionSummary[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [manifest, setManifest] = useState<CaptureSessionManifest>();
  const [mediaUrl, setMediaUrl] = useState<string>();
  const [imu, setImu] = useState<readonly ImuRow[]>([]);
  const [job, setJob] = useState<ExportJob>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    const abort = new AbortController();
    void (async () => {
      const items: SessionSummary[] = [];
      for await (const item of client.iterateSessions({ signal: abort.signal })) items.push(item);
      setSessions(items);
      setSessionId((current) => current || items[0]?.id || "");
    })().catch((reason: unknown) => setError(message(reason)));
    return () => abort.abort();
  }, [client]);

  useEffect(() => {
    if (!sessionId) return;
    const abort = new AbortController();
    let objectUrl: string | undefined;
    void (async () => {
      const next = await client.getManifest(sessionId, { signal: abort.signal });
      setManifest(next);
      const videoStream = next.streams.find((stream) => stream.kind === "video");
      const artifactId = videoStream?.artifactIds[0];
      if (artifactId !== undefined) {
        objectUrl = URL.createObjectURL(await client.getMediaArtifact(sessionId, artifactId, { signal: abort.signal }));
        setMediaUrl(objectUrl);
      }
    })().catch((reason: unknown) => setError(message(reason)));
    return () => { abort.abort(); if (objectUrl !== undefined) URL.revokeObjectURL(objectUrl); };
  }, [client, sessionId]);

  const refreshImu = async () => {
    const imuStream = manifest?.streams.find((stream) => stream.kind === "imu");
    const videoStream = manifest?.streams.find((stream) => stream.kind === "video");
    if (!imuStream || !videoStream) return;
    const playhead = videoStream.startNs + BigInt(Math.round((video.current?.currentTime ?? 0) * 1e9));
    const startNs = playhead < imuStream.startNs ? imuStream.startNs : playhead;
    const endNs = startNs + 1_000_000_000n < imuStream.endNs ? startNs + 1_000_000_000n : imuStream.endNs;
    if (endNs <= startNs) return;
    const range = await client.getSampleRange(sessionId, imuStream.id, { startNs, endNs, format: "json" });
    setImu(Array.isArray(range.data) ? range.data as readonly ImuRow[] : []);
  };

  const exportWindow = async () => {
    if (!manifest) return;
    const created = await client.createExport(
      { sessionId, startNs: manifest.startNs, endNs: manifest.endNs, sensorFormat: "json" },
      { idempotencyKey: crypto.randomUUID() }
    );
    setJob(created);
    setJob(await client.getExport(created.id));
  };

  return <main>
    <h1>AeroMaint minimal viewer</h1>
    <label>Session <select value={sessionId} onChange={(event) => setSessionId(event.target.value)}>
      {sessions.map((session) => <option key={session.id} value={session.id}>{session.name ?? session.id}</option>)}
    </select></label>
    <video ref={video} src={mediaUrl} controls onTimeUpdate={() => { void refreshImu().catch((reason: unknown) => setError(message(reason))); }} />
    <button type="button" onClick={() => { void refreshImu(); }}>Refresh IMU window</button>
    <pre>{JSON.stringify(imu, (_, value: unknown) => typeof value === "bigint" ? value.toString() : value, 2)}</pre>
    <button type="button" onClick={() => { void exportWindow().catch((reason: unknown) => setError(message(reason))); }}>Export session</button>
    {job && <p>Export {job.id}: {job.status} ({Math.round(job.progress * 100)}%)</p>}
    {job?.manifestUrl && <a href={new URL(job.manifestUrl, baseUrl).toString()}>Download export manifest</a>}
    {error && <p role="alert">{error}</p>}
  </main>;
}

function message(reason: unknown): string {
  return reason instanceof CaptureSdkError ? `${reason.code}: ${reason.message}` : String(reason);
}
