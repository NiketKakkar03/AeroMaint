export type CopilotStatus =
  "draft" | "refused" | "approved" | "rejected" | "revised";

export interface CopilotCitation {
  readonly evidence_id: string;
  readonly source_url: string;
  readonly title: string;
  readonly locator: string;
}

export interface CopilotRun {
  readonly id: string;
  readonly session_id: string;
  readonly question: string;
  readonly status: CopilotStatus;
  readonly version: number;
  readonly refusal_reason: string | null;
  readonly recommendation: {
    readonly summary: string;
    readonly claims: readonly {
      readonly text: string;
      readonly citations: readonly CopilotCitation[];
    }[];
    readonly limitations: readonly string[];
  } | null;
}

export interface CopilotDataSource {
  askCopilot(sessionId: string, question: string): Promise<CopilotRun>;
  listCopilotRuns(sessionId: string): Promise<readonly CopilotRun[]>;
  reviewCopilotRun(
    id: string,
    action: "approved" | "rejected" | "revised",
    version: number,
    revisedSummary?: string
  ): Promise<CopilotRun>;
}
