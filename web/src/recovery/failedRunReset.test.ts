import { describe, expect, it } from "vitest";

import type { WorkflowCheckpoint } from "./workflowCheckpoint";
import { resetFailedTextCheckpoint, resetFailedVisionCheckpoint } from "./failedRunReset";

const checkpoint: WorkflowCheckpoint = {
  caseId: "case-1",
  analysisV2RunId: "text-failed",
  visionRunId: "vision-failed",
  retrievalRunId: "retrieval-old",
  groundingRunId: "grounding-old",
  policyEvaluationRunId: "policy-old",
  idempotencyKeys: {
    analysisV2: "text-key-old",
    vision: "vision-key-old",
    retrieval: "retrieval-key-old",
    grounding: "grounding-key-old",
    policy: "policy-key-old",
  },
};

describe("failed analysis checkpoint reset", () => {
  it("clears Text and downstream IDs while preserving the independent Vision result", () => {
    expect(resetFailedTextCheckpoint(checkpoint)).toEqual({
      caseId: "case-1",
      visionRunId: "vision-failed",
      idempotencyKeys: { vision: "vision-key-old" },
    });
    expect(checkpoint.analysisV2RunId).toBe("text-failed");
  });

  it("clears only Vision identity and keeps the Text-policy workflow intact", () => {
    expect(resetFailedVisionCheckpoint(checkpoint)).toEqual({
      caseId: "case-1",
      analysisV2RunId: "text-failed",
      retrievalRunId: "retrieval-old",
      groundingRunId: "grounding-old",
      policyEvaluationRunId: "policy-old",
      idempotencyKeys: {
        analysisV2: "text-key-old",
        retrieval: "retrieval-key-old",
        grounding: "grounding-key-old",
        policy: "policy-key-old",
      },
    });
  });
});
