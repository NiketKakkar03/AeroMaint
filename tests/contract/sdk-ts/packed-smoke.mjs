import { execFile } from "node:child_process";
import { readFile, unlink, writeFile } from "node:fs/promises";
import { promisify } from "node:util";

import {
  CaptureAbortError,
  CaptureClient,
  CaptureSdkError
} from "@aeromaint/capture-sdk";

const run = promisify(execFile);

if (
  typeof CaptureClient !== "function" ||
  typeof CaptureSdkError !== "function"
) {
  throw new Error("Packed SDK exports are incomplete");
}
const client = new CaptureClient({
  baseUrl: "https://example.invalid",
  fetch: async () => new Response("[]")
});
const page = await client.listSessions();
if (page.items.length !== 0)
  throw new Error("Packed SDK client returned unexpected sessions");

const aborted = new AbortController();
aborted.abort();
await client.listSessions({ signal: aborted.signal }).then(
  () => {
    throw new Error("Packed SDK ignored AbortSignal cancellation");
  },
  (error) => {
    if (!(error instanceof CaptureAbortError) || error.retryable)
      throw new Error("Packed SDK did not return a typed abort error");
  }
);

let attempts = 0;
const retryingClient = new CaptureClient({
  baseUrl: "https://example.invalid",
  retry: { maxAttempts: 2, baseDelayMs: 1, maxDelayMs: 1 },
  fetch: async () => {
    attempts += 1;
    return attempts === 1
      ? new Response("busy", { status: 503 })
      : Response.json([
          {
            id: "session-1",
            start_ns: "9007199254740993",
            end_ns: "9007199254740994"
          }
        ]);
  }
});
const retriedPage = await retryingClient.listSessions();
if (attempts !== 2 || typeof retriedPage.items[0]?.startNs !== "bigint")
  throw new Error("Packed SDK retry or bigint conversion failed");

const output = new URL("./imu-window.json", import.meta.url);
const preload = new URL("./mock-fetch.mjs", import.meta.url);
await writeFile(
  preload,
  `globalThis.fetch = async (input) => {
  const url = String(input);
  if (url.includes("/v1/sessions?")) return Response.json({ items: [{ id: "session-1", start_ns: "9007199254740993", end_ns: "9007199254740994" }] });
  if (url.includes("/streams/imu-main/samples?")) return Response.json({ start_ns: "9007199254740993", end_ns: "9007199254740994", items: [{ timestamp_ns: "9007199254740993", values: { ax: 1 } }] });
  return new Response("not found", { status: 404 });
};\n`
);
try {
  const baseUrl = "http://packed-consumer.invalid";
  const cli = new URL(
    "./node_modules/@aeromaint/typescript-export-cli/dist/cli.js",
    import.meta.url
  );
  const listed = await run(process.execPath, [
    "--import",
    preload.pathname,
    cli.pathname,
    "--base-url",
    baseUrl,
    "sessions"
  ]);
  if (!listed.stdout.includes("session-1\t9007199254740993\t9007199254740994"))
    throw new Error("Packed CLI did not list the expected session");
  await run(process.execPath, [
    "--import",
    preload.pathname,
    cli.pathname,
    "--base-url",
    baseUrl,
    "imu",
    "session-1",
    "imu-main",
    "9007199254740993",
    "9007199254740994",
    output.pathname,
    "--json"
  ]);
  const imu = JSON.parse(await readFile(output, "utf8"));
  if (imu[0]?.timestamp_ns !== "9007199254740993")
    throw new Error("Packed CLI did not export the expected IMU window");
} finally {
  await unlink(output).catch(() => undefined);
  await unlink(preload).catch(() => undefined);
}
process.stdout.write("packed SDK smoke test passed\n");
