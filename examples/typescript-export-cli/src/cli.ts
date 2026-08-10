#!/usr/bin/env node
import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import { CaptureClient, CaptureSdkError } from "@aeromaint/capture-sdk";

interface Arguments {
  readonly baseUrl: string;
  readonly token?: string;
  readonly command: "sessions" | "imu";
  readonly values: readonly string[];
}

function usage(): never {
  throw new Error(
    "Usage: aeromaint-export [--base-url URL] [--token TOKEN] sessions | " +
      "imu SESSION STREAM START_NS END_NS OUTPUT [--json]"
  );
}

function parseArguments(argv: readonly string[]): Arguments {
  let baseUrl = process.env.AEROMAINT_API_URL ?? "http://localhost:8000";
  let token = process.env.AEROMAINT_TOKEN;
  const values: string[] = [];
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--base-url") baseUrl = argv[++index] ?? usage();
    else if (value === "--token") token = argv[++index] ?? usage();
    else values.push(value ?? usage());
  }
  const command = values.shift();
  if (command !== "sessions" && command !== "imu") usage();
  return {
    baseUrl,
    command,
    values,
    ...(token === undefined ? {} : { token })
  };
}

async function main(): Promise<void> {
  const args = parseArguments(process.argv.slice(2));
  const controller = new AbortController();
  process.once("SIGINT", () => {
    controller.abort();
  });
  const client = new CaptureClient({
    baseUrl: args.baseUrl,
    ...(args.token === undefined ? {} : { auth: args.token })
  });

  if (args.command === "sessions") {
    for await (const session of client.iterateSessions({
      maxItems: 1_000,
      signal: controller.signal
    })) {
      process.stdout.write(
        `${session.id}\t${session.startNs.toString()}\t${session.endNs.toString()}\n`
      );
    }
    return;
  }

  const [sessionId, streamId, startValue, endValue, output, formatValue] =
    args.values;
  if (
    sessionId === undefined ||
    streamId === undefined ||
    startValue === undefined ||
    endValue === undefined ||
    output === undefined
  )
    usage();
  if (!/^-?\d+$/.test(startValue) || !/^-?\d+$/.test(endValue))
    throw new Error("START_NS and END_NS must be decimal integers");
  const format = formatValue === "--json" ? "json" : "arrow";
  const range = await client.getSampleRange(sessionId, streamId, {
    startNs: BigInt(startValue),
    endNs: BigInt(endValue),
    format,
    signal: controller.signal
  });
  const bytes =
    range.data instanceof ArrayBuffer
      ? new Uint8Array(range.data)
      : new TextEncoder().encode(
          JSON.stringify(
            range.data,
            (_, value: unknown) =>
              typeof value === "bigint" ? value.toString() : value,
            2
          )
        );
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, bytes);
  process.stdout.write(
    `Wrote ${String(bytes.byteLength)} bytes (${range.contentType}) to ${output}\n`
  );
}

try {
  await main();
} catch (error) {
  const message =
    error instanceof CaptureSdkError
      ? `${error.code}: ${error.message}`
      : error instanceof Error
        ? error.message
        : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
}
