import { describe, expect, it } from "vitest";

import { REPORT_WAIT_DELAYS_MS, reportWaitDelay } from "./reportWait";

describe("reportWaitDelay", () => {
  it("uses bounded exponential backoff and stops instead of polling forever", () => {
    expect(REPORT_WAIT_DELAYS_MS).toEqual([750, 1_500, 3_000, 6_000, 12_000]);
    expect(REPORT_WAIT_DELAYS_MS.every((delay, index) => index === 0 || delay === REPORT_WAIT_DELAYS_MS[index - 1]! * 2)).toBe(true);
    expect(reportWaitDelay(REPORT_WAIT_DELAYS_MS.length)).toBeNull();
    expect(reportWaitDelay(REPORT_WAIT_DELAYS_MS.length + 100)).toBeNull();
  });
});
