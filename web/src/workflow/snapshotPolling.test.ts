import { describe, expect, it } from "vitest";

import { workflowPollDelay, workflowWaitExpired } from "./snapshotPolling";

describe("workflow snapshot polling", () => {
  it("backs off exponentially and caps at 30 seconds", () => {
    expect([0, 1, 2, 3, 4, 5, 6].map((attempt) => workflowPollDelay(attempt))).toEqual([
      1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000,
    ]);
  });

  it("stops at the configured maximum wait", () => {
    expect(workflowWaitExpired(1_000, 120_999, 120_000)).toBe(false);
    expect(workflowWaitExpired(1_000, 121_000, 120_000)).toBe(true);
  });
});
