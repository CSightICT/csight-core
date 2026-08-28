import { describe, expect, it } from "vitest";

import { qualificationPresentation } from "./reviewPresentation";

describe("qualificationPresentation", () => {
  it("turns the technical qualification snapshot into operator-facing Korean statuses", () => {
    expect(qualificationPresentation({
      llm: { scope: "MOCK_QUALIFIED" },
      vision: { scope: "MOCK_QUALIFIED" },
      alignment: { scope: "NOT_AVAILABLE" },
      grounding: {
        scope: "NOT_AVAILABLE",
        model_family: "csight-mock-llm",
        model_revision: "deterministic",
      },
    })).toEqual([
      { label: "문의 내용 분석", status: "참고용 분석 결과 준비", tone: "ready" },
      { label: "이미지 분석", status: "참고용 분석 결과 준비", tone: "ready" },
      { label: "문의·이미지 일치 확인", status: "담당자 확인 필요", tone: "attention" },
      { label: "정책 근거 정합성", status: "담당자 확인 필요", tone: "attention" },
    ]);
  });

  it("fails to a readable neutral status for an empty snapshot", () => {
    expect(qualificationPresentation({})).toEqual([
      { label: "분석 상태", status: "기록된 결과 없음", tone: "neutral" },
    ]);
  });
});
