const MAX_BACKOFF_MS = 30_000;

export const DEFAULT_WORKFLOW_MAX_WAIT_MS = 120_000;

export function workflowPollDelay(attempt: number, baseMs = 1_000): number {
  if (attempt < 0 || !Number.isInteger(attempt)) throw new Error("attempt must be a non-negative integer");
  if (baseMs < 0 || !Number.isFinite(baseMs)) throw new Error("baseMs must be non-negative");
  return Math.min(MAX_BACKOFF_MS, baseMs * (2 ** Math.min(attempt, 6)));
}

export function workflowWaitExpired(startedAtMs: number, nowMs: number, maxWaitMs = DEFAULT_WORKFLOW_MAX_WAIT_MS): boolean {
  return nowMs - startedAtMs >= maxWaitMs;
}
