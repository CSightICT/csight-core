import type { WorkflowCheckpoint } from "./workflowCheckpoint";

export function resetFailedTextCheckpoint(
  checkpoint: WorkflowCheckpoint,
): WorkflowCheckpoint {
  const next: WorkflowCheckpoint = {
    ...checkpoint,
    idempotencyKeys: { ...checkpoint.idempotencyKeys },
  };
  delete next.analysisV2RunId;
  delete next.retrievalRunId;
  delete next.groundingRunId;
  delete next.policyEvaluationRunId;
  delete next.idempotencyKeys.analysisV2;
  delete next.idempotencyKeys.retrieval;
  delete next.idempotencyKeys.grounding;
  delete next.idempotencyKeys.policy;
  return next;
}

export function resetFailedVisionCheckpoint(
  checkpoint: WorkflowCheckpoint,
): WorkflowCheckpoint {
  const next: WorkflowCheckpoint = {
    ...checkpoint,
    idempotencyKeys: { ...checkpoint.idempotencyKeys },
  };
  delete next.visionRunId;
  delete next.idempotencyKeys.vision;
  return next;
}
