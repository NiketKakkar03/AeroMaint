import {
  CAPTURE_MANIFEST_SCHEMA_VERSION,
  ManifestValidationError,
  parseManifest,
  type CaptureSessionManifest,
  type CaptureStream,
  type StreamKind,
  type TimestampNs
} from "@aeromaint/contracts";

export type { CaptureSessionManifest, CaptureStream, StreamKind, TimestampNs };

export type CaptureSdkErrorCode =
  | "aborted"
  | "authentication_error"
  | "forbidden"
  | "http_error"
  | "invalid_response"
  | "invalid_manifest"
  | "not_found"
  | "rate_limited"
  | "transport_error"
  | "unsupported_schema";

export class CaptureSdkError extends Error {
  public constructor(
    message: string,
    public readonly code: CaptureSdkErrorCode,
    public readonly status?: number,
    public readonly retryable = false,
    options?: ErrorOptions
  ) {
    super(message, options);
    this.name = "CaptureSdkError";
  }
}

export class CaptureHttpError extends CaptureSdkError {
  public constructor(
    message: string,
    status: number,
    code: CaptureSdkErrorCode = "http_error",
    retryable = false
  ) {
    super(message, code, status, retryable);
    this.name = "CaptureHttpError";
  }
}

export class CaptureAbortError extends CaptureSdkError {
  public constructor(options?: ErrorOptions) {
    super("Capture request was aborted", "aborted", undefined, false, options);
    this.name = "CaptureAbortError";
  }
}

export class CaptureTransportError extends CaptureSdkError {
  public constructor(
    message: string,
    retryable: boolean,
    options?: ErrorOptions
  ) {
    super(message, "transport_error", undefined, retryable, options);
    this.name = "CaptureTransportError";
  }
}

export type AuthHeaders = Readonly<Record<string, string>>;
export type AuthProvider =
  string | AuthHeaders | (() => AuthHeaders | Promise<AuthHeaders>);

export interface RetryOptions {
  readonly maxAttempts?: number;
  readonly baseDelayMs?: number;
  readonly maxDelayMs?: number;
}

export interface CaptureClientOptions {
  readonly baseUrl: string;
  readonly fetch?: typeof globalThis.fetch;
  readonly auth?: AuthProvider;
  readonly headers?: AuthHeaders;
  readonly retry?: RetryOptions;
}

export interface RequestOptions {
  readonly signal?: AbortSignal;
}

export interface PageOptions extends RequestOptions {
  readonly cursor?: string;
  readonly limit?: number;
}

export interface IterationOptions extends RequestOptions {
  readonly pageSize?: number;
  readonly maxItems?: number;
}

export interface SessionSummary {
  readonly id: string;
  readonly name?: string;
  readonly startNs: TimestampNs;
  readonly endNs: TimestampNs;
  readonly streamCount?: number;
}

export interface Page<T> {
  readonly items: readonly T[];
  readonly nextCursor?: string;
}

export interface StreamSummary {
  readonly id: string;
  readonly kind: StreamKind;
  readonly startNs: TimestampNs;
  readonly endNs: TimestampNs;
  readonly schemaRef?: string;
}

export interface SampleRangeRequest extends RequestOptions {
  readonly startNs: TimestampNs;
  readonly endNs: TimestampNs;
  readonly cursor?: string;
  readonly limit?: number;
  readonly format?: "arrow" | "json";
}

export interface SampleRange {
  readonly sessionId: string;
  readonly streamId: string;
  readonly startNs: TimestampNs;
  readonly endNs: TimestampNs;
  readonly contentType: string;
  readonly data: unknown;
  readonly nextCursor?: string;
}

export interface FrameLookupRequest extends RequestOptions {
  readonly timestampNs: TimestampNs;
  readonly mode?: "at_or_before" | "nearest";
}

export interface FrameLookup {
  readonly streamId: string;
  readonly frameNumber: number;
  readonly presentationNs: TimestampNs;
  readonly keyframe: boolean;
  readonly mediaUrl?: string;
}

interface ResolvedRetryOptions {
  readonly maxAttempts: number;
  readonly baseDelayMs: number;
  readonly maxDelayMs: number;
}

const DEFAULT_RETRY: ResolvedRetryOptions = {
  maxAttempts: 3,
  baseDelayMs: 100,
  maxDelayMs: 2_000
};

function record(value: unknown, context: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new CaptureSdkError(
      `${context} must be an object`,
      "invalid_response"
    );
  }
  return value as Record<string, unknown>;
}

function stringField(value: unknown, context: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new CaptureSdkError(
      `${context} must be a non-empty string`,
      "invalid_response"
    );
  }
  return value;
}

function numberField(value: unknown, context: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new CaptureSdkError(
      `${context} must be a non-negative integer`,
      "invalid_response"
    );
  }
  return value;
}

function timestamp(value: unknown, context: string): TimestampNs {
  if (typeof value !== "string" || !/^-?\d+$/.test(value)) {
    throw new CaptureSdkError(
      `${context} must be a decimal string`,
      "invalid_response"
    );
  }
  return BigInt(value);
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function normalizeNanoseconds(value: unknown, key = ""): unknown {
  if (
    typeof value === "string" &&
    /(?:^|_)ns$/.test(key) &&
    /^-?\d+$/.test(value)
  ) {
    return BigInt(value);
  }
  if (Array.isArray(value))
    return value.map((item) => normalizeNanoseconds(item));
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value).map(([field, item]) => [
        field,
        normalizeNanoseconds(item, field)
      ])
    );
  }
  return value;
}

function pageEnvelope(value: unknown): {
  items: readonly unknown[];
  nextCursor?: string;
} {
  if (Array.isArray(value)) return { items: value };
  const root = record(value, "Page response");
  const candidate = root.items ?? root.sessions ?? root.streams ?? root.data;
  if (!Array.isArray(candidate)) {
    throw new CaptureSdkError(
      "Page response does not contain an item array",
      "invalid_response"
    );
  }
  const cursor = optionalString(
    root.next_cursor ?? root.nextCursor ?? root.cursor
  );
  return cursor === undefined
    ? { items: candidate }
    : { items: candidate, nextCursor: cursor };
}

function sessionSummary(value: unknown): SessionSummary {
  const item = record(value, "Session");
  const result: SessionSummary = {
    id: stringField(item.id ?? item.session_id, "Session id"),
    startNs: timestamp(item.start_ns ?? item.startNs, "Session start_ns"),
    endNs: timestamp(item.end_ns ?? item.endNs, "Session end_ns")
  };
  const name = optionalString(item.name);
  const streamCountValue = item.stream_count ?? item.streamCount;
  return {
    ...result,
    ...(name === undefined ? {} : { name }),
    ...(streamCountValue === undefined
      ? {}
      : { streamCount: numberField(streamCountValue, "Session stream_count") })
  };
}

const STREAM_KINDS = new Set<StreamKind>([
  "video",
  "imu",
  "pose",
  "event",
  "telemetry"
]);

function streamSummary(value: unknown): StreamSummary {
  const item = record(value, "Stream");
  const kind = stringField(item.kind, "Stream kind");
  if (!STREAM_KINDS.has(kind as StreamKind)) {
    throw new CaptureSdkError(
      `Unsupported stream kind ${kind}`,
      "invalid_response"
    );
  }
  const schemaRef = optionalString(item.schema_ref ?? item.schemaRef);
  return {
    id: stringField(item.id ?? item.stream_id, "Stream id"),
    kind: kind as StreamKind,
    startNs: timestamp(item.start_ns ?? item.startNs, "Stream start_ns"),
    endNs: timestamp(item.end_ns ?? item.endNs, "Stream end_ns"),
    ...(schemaRef === undefined ? {} : { schemaRef })
  };
}

function parseFrame(value: unknown, streamId: string): FrameLookup | undefined {
  if (value === null) return undefined;
  const envelope = record(value, "Frame response");
  const item = record(envelope.frame ?? envelope.data ?? envelope, "Frame");
  const mediaUrl = optionalString(item.media_url ?? item.mediaUrl ?? item.url);
  return {
    streamId: optionalString(item.stream_id ?? item.streamId) ?? streamId,
    frameNumber: numberField(
      item.frame_number ?? item.frameNumber,
      "Frame number"
    ),
    presentationNs: timestamp(
      item.presentation_ns ?? item.presentationNs ?? item.timestamp_ns,
      "Frame presentation_ns"
    ),
    keyframe: item.keyframe === true,
    ...(mediaUrl === undefined ? {} : { mediaUrl })
  };
}

function sdkErrorForResponse(status: number, detail: string): CaptureHttpError {
  const suffix = detail.length === 0 ? "" : `: ${detail}`;
  if (status === 401)
    return new CaptureHttpError(
      `Authentication failed${suffix}`,
      status,
      "authentication_error"
    );
  if (status === 403)
    return new CaptureHttpError(
      `Request is forbidden${suffix}`,
      status,
      "forbidden"
    );
  if (status === 404)
    return new CaptureHttpError(
      `Resource was not found${suffix}`,
      status,
      "not_found"
    );
  if (status === 429)
    return new CaptureHttpError(
      `Request was rate limited${suffix}`,
      status,
      "rate_limited",
      true
    );
  const retryable = status === 408 || status >= 500;
  return new CaptureHttpError(
    `Request failed with HTTP ${String(status)}${suffix}`,
    status,
    "http_error",
    retryable
  );
}

function abortError(error?: unknown): CaptureAbortError {
  return new CaptureAbortError(
    error instanceof Error ? { cause: error } : undefined
  );
}

function isAborted(signal: AbortSignal | undefined): boolean {
  return signal?.aborted === true;
}

function validateBound(
  value: number | undefined,
  fallback: number,
  name: string
): number {
  const resolved = value ?? fallback;
  if (!Number.isSafeInteger(resolved) || resolved <= 0) {
    throw new RangeError(`${name} must be a positive integer`);
  }
  return resolved;
}

function addQuery(
  path: string,
  values: Readonly<Record<string, string | number | undefined>>
): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const encoded = query.toString();
  return encoded.length === 0 ? path : `${path}?${encoded}`;
}

async function wait(delayMs: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted === true) throw abortError(signal.reason);
  await new Promise<void>((resolve, reject) => {
    const finish = (): void => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    };
    const timer = setTimeout(finish, delayMs);
    const onAbort = (): void => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      reject(abortError(signal?.reason));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export class CaptureClient {
  readonly #baseUrl: string;
  readonly #fetch: typeof globalThis.fetch;
  readonly #auth: AuthProvider | undefined;
  readonly #headers: AuthHeaders;
  readonly #retry: ResolvedRetryOptions;

  public constructor(options: CaptureClientOptions) {
    if (!/^https?:\/\//.test(options.baseUrl))
      throw new TypeError("baseUrl must be an HTTP(S) URL");
    this.#baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.#fetch = options.fetch ?? globalThis.fetch;
    this.#auth = options.auth;
    this.#headers = options.headers ?? {};
    this.#retry = {
      maxAttempts: validateBound(
        options.retry?.maxAttempts,
        DEFAULT_RETRY.maxAttempts,
        "maxAttempts"
      ),
      baseDelayMs: validateBound(
        options.retry?.baseDelayMs,
        DEFAULT_RETRY.baseDelayMs,
        "baseDelayMs"
      ),
      maxDelayMs: validateBound(
        options.retry?.maxDelayMs,
        DEFAULT_RETRY.maxDelayMs,
        "maxDelayMs"
      )
    };
  }

  async #authHeaders(): Promise<AuthHeaders> {
    if (typeof this.#auth === "string")
      return { authorization: `Bearer ${this.#auth}` };
    if (typeof this.#auth === "function") return await this.#auth();
    return this.#auth ?? {};
  }

  async #request(path: string, init: RequestInit = {}): Promise<Response> {
    const signal = init.signal === null ? undefined : init.signal;
    if (signal?.aborted === true) throw abortError(signal.reason);
    const authHeaders = await this.#authHeaders();
    let lastError: CaptureSdkError | undefined;
    for (let attempt = 1; attempt <= this.#retry.maxAttempts; attempt += 1) {
      try {
        const response = await this.#fetch(`${this.#baseUrl}${path}`, {
          ...init,
          headers: {
            ...this.#headers,
            ...authHeaders,
            ...Object.fromEntries(new Headers(init.headers))
          },
          signal: signal ?? null
        });
        if (response.ok) return response;
        const detail = await response.text();
        const error = sdkErrorForResponse(
          response.status,
          detail.slice(0, 500)
        );
        if (!error.retryable || attempt === this.#retry.maxAttempts)
          throw error;
        lastError = error;
        const retryAfter = Number(response.headers.get("retry-after"));
        const delay =
          Number.isFinite(retryAfter) && retryAfter >= 0
            ? retryAfter * 1_000
            : Math.min(
                this.#retry.baseDelayMs * 2 ** (attempt - 1),
                this.#retry.maxDelayMs
              );
        await wait(delay, signal);
      } catch (error) {
        if (error instanceof CaptureSdkError) {
          if (!error.retryable || attempt === this.#retry.maxAttempts)
            throw error;
          lastError = error;
        } else {
          if (
            isAborted(signal) ||
            (error instanceof DOMException && error.name === "AbortError")
          ) {
            throw abortError(error);
          }
          lastError = new CaptureTransportError(
            `Capture request failed: ${String(error)}`,
            true,
            error instanceof Error ? { cause: error } : undefined
          );
          if (attempt === this.#retry.maxAttempts) throw lastError;
        }
        await wait(
          Math.min(
            this.#retry.baseDelayMs * 2 ** (attempt - 1),
            this.#retry.maxDelayMs
          ),
          signal
        );
      }
    }
    throw (
      lastError ?? new CaptureTransportError("Capture request failed", true)
    );
  }

  public async listSessions(
    options: PageOptions = {}
  ): Promise<Page<SessionSummary>> {
    const path = addQuery("/v1/sessions", {
      cursor: options.cursor,
      limit: options.limit
    });
    const envelope = pageEnvelope(
      await (
        await this.#request(path, { signal: options.signal ?? null })
      ).json()
    );
    return {
      items: envelope.items.map(sessionSummary),
      ...(envelope.nextCursor === undefined
        ? {}
        : { nextCursor: envelope.nextCursor })
    };
  }

  public async *iterateSessions(
    options: IterationOptions = {}
  ): AsyncGenerator<SessionSummary> {
    const pageSize = validateBound(options.pageSize, 100, "pageSize");
    const maxItems = validateBound(options.maxItems, 1_000, "maxItems");
    let cursor: string | undefined;
    let emitted = 0;
    do {
      const page = await this.listSessions({
        limit: Math.min(pageSize, maxItems - emitted),
        ...(cursor === undefined ? {} : { cursor }),
        ...(options.signal === undefined ? {} : { signal: options.signal })
      });
      for (const item of page.items) {
        if (emitted >= maxItems) return;
        emitted += 1;
        yield item;
      }
      if (
        page.items.length === 0 ||
        page.nextCursor === undefined ||
        page.nextCursor === cursor
      )
        return;
      cursor = page.nextCursor;
    } while (emitted < maxItems);
  }

  public async getSessionManifest(
    sessionId: string,
    signal?: AbortSignal
  ): Promise<CaptureSessionManifest> {
    const response = await this.#request(
      `/v1/sessions/${encodeURIComponent(sessionId)}/manifest`,
      { signal: signal ?? null }
    );
    const payload: unknown = await response.json();
    const root = record(payload, "Manifest response");
    const manifestPayload = root.manifest ?? root.data ?? payload;
    const manifestRoot = record(manifestPayload, "Manifest");
    const version = optionalString(manifestRoot.schema_version);
    if (version === undefined)
      throw new CaptureSdkError(
        "Response is not a capture manifest",
        "invalid_manifest"
      );
    if (version !== CAPTURE_MANIFEST_SCHEMA_VERSION) {
      throw new CaptureSdkError(
        `Unsupported manifest schema ${version}`,
        "unsupported_schema"
      );
    }
    try {
      return parseManifest(manifestPayload);
    } catch (error) {
      throw new CaptureSdkError(
        error instanceof ManifestValidationError
          ? `Invalid manifest at ${error.path}: ${error.message}`
          : `Manifest validation failed: ${String(error)}`,
        "invalid_manifest",
        undefined,
        false,
        error instanceof Error ? { cause: error } : undefined
      );
    }
  }

  public getManifest(
    sessionId: string,
    options: RequestOptions = {}
  ): Promise<CaptureSessionManifest> {
    return this.getSessionManifest(sessionId, options.signal);
  }

  public async listStreams(
    sessionId: string,
    options: PageOptions = {}
  ): Promise<Page<StreamSummary>> {
    const path = addQuery(
      `/v1/sessions/${encodeURIComponent(sessionId)}/streams`,
      { cursor: options.cursor, limit: options.limit }
    );
    const response = await this.#request(path, {
      signal: options.signal ?? null
    });
    const envelope = pageEnvelope(await response.json());
    return {
      items: envelope.items.map(streamSummary),
      ...(envelope.nextCursor === undefined
        ? {}
        : { nextCursor: envelope.nextCursor })
    };
  }

  public async *iterateStreams(
    sessionId: string,
    options: IterationOptions = {}
  ): AsyncGenerator<StreamSummary> {
    const pageSize = validateBound(options.pageSize, 100, "pageSize");
    const maxItems = validateBound(options.maxItems, 1_000, "maxItems");
    let cursor: string | undefined;
    let emitted = 0;
    do {
      const page = await this.listStreams(sessionId, {
        limit: Math.min(pageSize, maxItems - emitted),
        ...(cursor === undefined ? {} : { cursor }),
        ...(options.signal === undefined ? {} : { signal: options.signal })
      });
      for (const item of page.items) {
        if (emitted >= maxItems) return;
        emitted += 1;
        yield item;
      }
      if (
        page.items.length === 0 ||
        page.nextCursor === undefined ||
        page.nextCursor === cursor
      )
        return;
      cursor = page.nextCursor;
    } while (emitted < maxItems);
  }

  public async getSampleRange(
    sessionId: string,
    streamId: string,
    request: SampleRangeRequest
  ): Promise<SampleRange> {
    if (request.endNs < request.startNs)
      throw new RangeError("endNs must be greater than or equal to startNs");
    const path = addQuery(
      `/v1/sessions/${encodeURIComponent(sessionId)}/streams/${encodeURIComponent(streamId)}/samples`,
      {
        start_ns: request.startNs.toString(),
        end_ns: request.endNs.toString(),
        cursor: request.cursor,
        limit: request.limit,
        format: request.format
      }
    );
    const response = await this.#request(path, {
      headers: {
        accept:
          request.format === "json"
            ? "application/json"
            : "application/vnd.apache.arrow.stream, application/json;q=0.5"
      },
      signal: request.signal ?? null
    });
    const contentType =
      response.headers.get("content-type")?.split(";", 1)[0] ??
      "application/octet-stream";
    if (contentType === "application/json" || contentType.endsWith("+json")) {
      const payload: unknown = await response.json();
      const root = record(payload, "Sample range");
      const nextCursor = optionalString(root.next_cursor ?? root.nextCursor);
      return {
        sessionId,
        streamId,
        startNs: timestamp(
          root.start_ns ?? request.startNs.toString(),
          "Sample range start_ns"
        ),
        endNs: timestamp(
          root.end_ns ?? request.endNs.toString(),
          "Sample range end_ns"
        ),
        contentType,
        data: normalizeNanoseconds(
          root.samples ?? root.data ?? root.items ?? payload
        ),
        ...(nextCursor === undefined ? {} : { nextCursor })
      };
    }
    const nextCursor = optionalString(response.headers.get("x-next-cursor"));
    return {
      sessionId,
      streamId,
      startNs: request.startNs,
      endNs: request.endNs,
      contentType,
      data: await response.arrayBuffer(),
      ...(nextCursor === undefined ? {} : { nextCursor })
    };
  }

  public async lookupFrame(
    sessionId: string,
    streamId: string,
    request: FrameLookupRequest
  ): Promise<FrameLookup | undefined> {
    const path = addQuery(
      `/v1/sessions/${encodeURIComponent(sessionId)}/streams/${encodeURIComponent(streamId)}/frames/lookup`,
      {
        timestamp_ns: request.timestampNs.toString(),
        mode: request.mode ?? "at_or_before"
      }
    );
    const response = await this.#request(path, {
      signal: request.signal ?? null
    });
    if (response.status === 204) return undefined;
    return parseFrame(await response.json(), streamId);
  }
}
