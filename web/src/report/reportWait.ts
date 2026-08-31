export const REPORT_WAIT_DELAYS_MS = [750, 1_500, 3_000, 6_000, 12_000] as const;

export function reportWaitDelay(attempt: number): number | null {
  return REPORT_WAIT_DELAYS_MS[attempt] ?? null;
}
