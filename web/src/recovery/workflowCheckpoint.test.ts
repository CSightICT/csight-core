import { describe, expect, it } from "vitest";

import { checkpointStore, workflowCheckpointSchema } from "./workflowCheckpoint";

describe("workflow checkpoint", () => {
  it("persists opaque IDs and idempotency keys only", () => {
    checkpointStore.save({
      caseId: "case-1",
      analysisV2RunId: "analysis-1",
      idempotencyKeys: { analysisV2: "key-1" },
    });
    expect(JSON.parse(sessionStorage.getItem("csight.workflow.v1")!)).toEqual({
      caseId: "case-1", analysisV2RunId: "analysis-1", idempotencyKeys: { analysisV2: "key-1" },
    });
  });

  it("rejects customer text, tokens, URLs, and unknown nested fields", () => {
    expect(workflowCheckpointSchema.safeParse({ caseId: "case-1", idempotencyKeys: {}, customer_message: "sensitive" }).success).toBe(false);
    expect(workflowCheckpointSchema.safeParse({ caseId: "case-1", idempotencyKeys: { token: "secret" } }).success).toBe(false);
    expect(workflowCheckpointSchema.safeParse({ caseId: "https://signed.example/evidence", idempotencyKeys: {} }).success).toBe(false);
  });
});
