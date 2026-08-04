import {
  CAPTURE_MANIFEST_SCHEMA_VERSION,
  parseManifest,
  type CaptureSessionManifest,
  type CaptureSessionManifestJson
} from "@aeromaint/contracts";

export class CaptureSdkError extends Error {
  public constructor(
    message: string,
    public readonly code:
      "http_error" | "invalid_manifest" | "unsupported_schema",
    public readonly status?: number
  ) {
    super(message);
    this.name = "CaptureSdkError";
  }
}

export interface CaptureClientOptions {
  readonly baseUrl: string;
  readonly fetch?: typeof globalThis.fetch;
}

interface UnversionedManifestJson {
  readonly schema_version: string;
  readonly session_id: string;
  readonly display_name: string;
  readonly start_ns: string;
  readonly end_ns: string;
  readonly streams: readonly unknown[];
}

function isManifestJson(value: unknown): value is UnversionedManifestJson {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.schema_version === "string" &&
    typeof candidate.session_id === "string" &&
    typeof candidate.display_name === "string" &&
    typeof candidate.start_ns === "string" &&
    typeof candidate.end_ns === "string" &&
    Array.isArray(candidate.streams)
  );
}

export class CaptureClient {
  readonly #baseUrl: string;
  readonly #fetch: typeof globalThis.fetch;

  public constructor(options: CaptureClientOptions) {
    this.#baseUrl = options.baseUrl.replace(/\/$/, "");
    this.#fetch = options.fetch ?? globalThis.fetch;
  }

  public async getSessionManifest(
    sessionId: string,
    signal?: AbortSignal
  ): Promise<CaptureSessionManifest> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/sessions/${encodeURIComponent(sessionId)}/manifest`,
      { signal: signal ?? null }
    );
    if (!response.ok) {
      throw new CaptureSdkError(
        `Manifest request failed with HTTP ${String(response.status)}`,
        "http_error",
        response.status
      );
    }

    const payload: unknown = await response.json();
    if (!isManifestJson(payload)) {
      throw new CaptureSdkError(
        "Response is not a capture manifest",
        "invalid_manifest"
      );
    }
    if (payload.schema_version !== CAPTURE_MANIFEST_SCHEMA_VERSION) {
      throw new CaptureSdkError(
        `Unsupported manifest schema ${payload.schema_version}`,
        "unsupported_schema"
      );
    }

    try {
      return parseManifest(payload as CaptureSessionManifestJson);
    } catch (error) {
      throw new CaptureSdkError(
        `Manifest contains an invalid timestamp: ${String(error)}`,
        "invalid_manifest"
      );
    }
  }
}
