import { z } from "zod";

const KEY = "csight.workflow.v1";

const opaqueId = z.string().min(1).max(200).regex(/^[A-Za-z0-9._:-]+$/);
const idempotencyKeys = z.object({
  analysisV2: opaqueId.optional(),
  vision: opaqueId.optional(),
  retrieval: opaqueId.optional(),
  grounding: opaqueId.optional(),
  policy: opaqueId.optional(),
}).strict();

export const workflowCheckpointSchema = z.object({
  caseId: opaqueId,
  analysisV2RunId: opaqueId.optional(),
  visionRunId: opaqueId.optional(),
  retrievalRunId: opaqueId.optional(),
  groundingRunId: opaqueId.optional(),
  policyEvaluationRunId: opaqueId.optional(),
  idempotencyKeys,
}).strict();

export type WorkflowCheckpoint = z.infer<typeof workflowCheckpointSchema>;

export const checkpointStore = {
  load(caseId: string): WorkflowCheckpoint {
    const fallback = { caseId, idempotencyKeys: {} };
    try {
      const raw = sessionStorage.getItem(KEY);
      if (!raw) return fallback;
      const parsed = workflowCheckpointSchema.safeParse(JSON.parse(raw));
      return parsed.success && parsed.data.caseId === caseId ? parsed.data : fallback;
    } catch {
      return fallback;
    }
  },
  save(checkpoint: WorkflowCheckpoint): void {
    sessionStorage.setItem(KEY, JSON.stringify(workflowCheckpointSchema.parse(checkpoint)));
  },
  patch(caseId: string, patch: Partial<WorkflowCheckpoint>): WorkflowCheckpoint {
    const current = this.load(caseId);
    const next = workflowCheckpointSchema.parse({ ...current, ...patch, caseId });
    this.save(next);
    return next;
  },
  clear(): void {
    sessionStorage.removeItem(KEY);
  },
};

export function newOpaqueKey(): string {
  return crypto.randomUUID();
}
