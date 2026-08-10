import { CaptureClient } from "@aeromaint/capture-sdk";

const baseUrl = process.env.AEROMAINT_API_URL ?? "http://127.0.0.1:8000";
const client = new CaptureClient({
  baseUrl,
  auth: process.env.AEROMAINT_TOKEN
});
const sessions = [];
for await (const session of client.iterateSessions({ maxItems: 10 }))
  sessions.push(session);
if (sessions.length === 0) throw new Error("Live API returned no sessions");
const manifest = await client.getSessionManifest(sessions[0].id);
if (manifest.sessionId !== sessions[0].id)
  throw new Error("Session and manifest IDs disagree");
if (typeof manifest.startNs !== "bigint")
  throw new Error("Manifest timestamps are not bigint");
process.stdout.write(
  `Validated ${manifest.sessionId} with ${String(manifest.streams.length)} streams\n`
);
