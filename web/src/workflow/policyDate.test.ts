import { describe, expect, it } from "vitest";

import { policyAsOfDate } from "./policyDate";

describe("policyAsOfDate", () => {
  it("uses the Korean business date when a UTC receipt crosses midnight in Seoul", () => {
    expect(policyAsOfDate("2026-08-27T17:47:03.77151Z")).toBe("2026-08-28");
  });

  it("fails before an API request when the receipt time is invalid", () => {
    expect(() => policyAsOfDate("not-a-date")).toThrow("정책 기준일을 확인할 수 없습니다");
  });
});
