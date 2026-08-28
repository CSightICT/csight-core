import { describe, expect, it } from "vitest";

import { businessLabel } from "./businessLabels";

describe("businessLabel", () => {
  it("shows business language instead of internal decision and resolution codes", () => {
    expect(businessLabel("APPROVE_REFUND")).toBe("환불 승인");
    expect(businessLabel("ACTION_NEEDS_INPUT")).toBe("처리 정보 보완 필요");
    expect(businessLabel("SIMULATED_NOT_SENT")).toContain("실제 발송 없음");
    expect(businessLabel("EXCHANGE")).toBe("교환");
    expect(businessLabel("SAFETY_REVIEW")).toBe("안전 검토");
    expect(businessLabel("CRITICAL")).toBe("긴급");
    expect(businessLabel("REQUIRES_HUMAN_REVIEW")).toBe("담당자 확인 후 결정 필요");
    expect(businessLabel("MOCK_QUALIFIED")).toBe("참고용 분석 결과 준비");
  });
});
