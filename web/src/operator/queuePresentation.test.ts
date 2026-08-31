import { describe, expect, it } from "vitest";

import { formatQueueWait } from "./queuePresentation";

describe("formatQueueWait", () => {
  const now = new Date("2026-08-29T12:00:00Z").getTime();

  it("presents operator wait time in compact Korean units and fails soft", () => {
    expect(formatQueueWait("2026-08-29T11:59:45Z", now)).toBe("방금");
    expect(formatQueueWait("2026-08-29T11:42:00Z", now)).toBe("18분");
    expect(formatQueueWait("2026-08-29T08:00:00Z", now)).toBe("4시간");
    expect(formatQueueWait("2026-08-27T08:00:00Z", now)).toBe("2일");
    expect(formatQueueWait("not-a-date", now)).toBe("시간 확인 필요");
  });
});
