import { describe, expect, it } from "vitest";

import type { ReviewTaskDetail } from "../api/contracts";
import { QUICK_REVIEW_READINESS_THRESHOLD, assessQuickReview, quickResolveInput } from "./quickReview";

function detail(overrides: Partial<ReviewTaskDetail> = {}): ReviewTaskDetail {
  return {
    task: {
      id: "task-1", case_id: "case-1", policy_evaluation_run_id: "policy-1",
      task_type: "STANDARD_REVIEW", priority: "NORMAL", status: "PENDING",
      current_assignee_id: null, version: 1, mapping_rule_name: "review_task_mapping",
      mapping_rule_version: "1.0.0", created_at: "2026-08-28T00:00:00Z",
      updated_at: "2026-08-28T00:00:00Z", resolved_at: null,
    },
    packet: {
      policy_summary_status: "REQUIRES_HUMAN_REVIEW",
      qualification_snapshot: { llm: { scope: "MOCK_QUALIFIED" } },
      llm_extraction_result_v2_id: "analysis-1",
      policy_effects: [{ type: "MARK_REVIEW_ELIGIBILITY", value: "REPAIR_REVIEW" }],
    },
    actions: [], decision: null,
    rule_results: [{ id: "rule-result-1", rule_id: "RULE-1", status: "MATCHED" }],
    citation_items: [{ citation_id: "citation-1", clause_id: "CLAUSE-1" }],
    grounded_explanation: null,
    inquiry_summary: null,
    policy_similarity: [],
    ...overrides,
  };
}

describe("PoC quick review", () => {
  it("uses a 0.70 readiness gate and maps policy eligibility to the allow decision", () => {
    const assessment = assessQuickReview(detail());
    expect(QUICK_REVIEW_READINESS_THRESHOLD).toBe(0.7);
    expect(assessment).toMatchObject({ score: 1, eligible: true, allowDecision: "APPROVE_REPAIR", allowLabel: "수리 허용" });
    expect(quickResolveInput(assessment, "ALLOW", 2)).toEqual({
      expected_version: 2,
      decision: "APPROVE_REPAIR",
      reason_codes: ["POLICY_CONDITION_MET"],
      rationale: "담당자가 고정된 정책 규칙과 인용 근거를 확인하고 요청 처리를 허용했습니다.",
      basis: [
        { type: "POLICY_RULE_RESULT", reference_id: "rule-result-1" },
        { type: "POLICY_CITATION", reference_id: "citation-1" },
      ],
    });
  });

  it("records a human rejection even when no single allow action can be mapped", () => {
    const assessment = assessQuickReview(detail({
      packet: {
        policy_summary_status: "REQUIRES_HUMAN_REVIEW",
        qualification_snapshot: { llm: { scope: "MOCK_QUALIFIED" } },
        policy_effects: [{ type: "MARK_REVIEW_ELIGIBILITY", value: "ACTION_REVIEW" }],
      },
    }));
    expect(assessment).toMatchObject({ score: 0.85, eligible: true, allowDecision: null });
    expect(quickResolveInput(assessment, "DENY", 1).decision).toBe("REJECT_REQUEST");
    expect(() => quickResolveInput(assessment, "ALLOW", 1)).toThrow("허용 처리 유형");
  });

  it("blocks one-click decisions when policy asks for more evidence", () => {
    const assessment = assessQuickReview(detail({
      packet: {
        policy_summary_status: "REQUIRES_ADDITIONAL_EVIDENCE",
        qualification_snapshot: { llm: { scope: "MOCK_QUALIFIED" } },
        policy_effects: [{ type: "MARK_REVIEW_ELIGIBILITY", value: "EXCHANGE_REVIEW" }],
      },
    }));
    expect(assessment.eligible).toBe(false);
    expect(assessment.blockers).toContain("추가 자료 요청 또는 정책 입력 확인이 먼저 필요합니다.");
  });
});
