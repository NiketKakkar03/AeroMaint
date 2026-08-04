import {
  CAPTURE_MANIFEST_SCHEMA_VERSION,
  ManifestValidationError,
  parseManifest,
  type CaptureSessionManifest
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

function schemaVersion(value: unknown): string | undefined {
  if (typeof value !== "object" || value === null) return undefined;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.schema_version === "string"
    ? candidate.schema_version
    : undefined;
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
    const version = schemaVersion(payload);
    if (version === undefined) {
      throw new CaptureSdkError(
        "Response is not a capture manifest",
        "invalid_manifest"
      );
    }
    if (version !== CAPTURE_MANIFEST_SCHEMA_VERSION) {
      throw new CaptureSdkError(
        `Unsupported manifest schema ${version}`,
        "unsupported_schema"
      );
    }

    try {
      return parseManifest(payload);
    } catch (error) {
      throw new CaptureSdkError(
        error instanceof ManifestValidationError
          ? `Invalid manifest at ${String(error.path)}: ${String(error.message)}`
          : `Manifest validation failed: ${String(error)}`,
        "invalid_manifest"
      );
    }
  }
}
