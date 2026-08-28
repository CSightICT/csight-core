import type { ResolveInput } from "../api/client";
import type { ReviewTaskDetail } from "../api/contracts";

export const QUICK_REVIEW_READINESS_THRESHOLD = 0.7;

export type QuickReviewVerdict = "ALLOW" | "DENY";

export interface BasisOption {
  type: "POLICY_RULE_RESULT" | "POLICY_CITATION" | "ANALYSIS_RESULT";
  reference_id: string;
  label: string;
}

export interface QuickReviewAssessment {
  score: number;
  threshold: number;
  eligible: boolean;
  allowDecision: string | null;
  allowLabel: string;
  basis: BasisOption[];
  blockers: string[];
}

const eligibilityDecision: Record<string, string> = {
  RETURN_REVIEW: "APPROVE_REFUND",
  REFUND_REVIEW: "APPROVE_REFUND",
  EXCHANGE_REVIEW: "APPROVE_EXCHANGE",
  RESHIPMENT_REVIEW: "APPROVE_RESHIPMENT",
  REPAIR_REVIEW: "APPROVE_REPAIR",
};

const decisionLabels: Record<string, string> = {
  APPROVE_REFUND: "환불/반품 허용",
  APPROVE_EXCHANGE: "교환 허용",
  APPROVE_RESHIPMENT: "재배송 허용",
  APPROVE_REPAIR: "수리 허용",
};

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function reviewBasisOptions(detail: ReviewTaskDetail): BasisOption[] {
  const options: BasisOption[] = [];
  detail.rule_results.forEach((rule) => {
    const id = text(rule.id ?? rule.rule_result_id ?? rule.rule_id);
    if (id) options.push({
      type: "POLICY_RULE_RESULT",
      reference_id: id,
      label: `규칙 ${String(rule.rule_id ?? id)} · ${String(rule.status ?? "확인")}`,
    });
  });
  detail.citation_items.forEach((citation, index) => {
    const id = text(citation.citation_id ?? citation.id);
    if (id) options.push({
      type: "POLICY_CITATION",
      reference_id: id,
      label: `인용 ${index + 1} · ${String(citation.clause_id ?? id)}`,
    });
  });
  const extraction = text(detail.packet.llm_extraction_result_v2_id);
  if (extraction) options.push({
    type: "ANALYSIS_RESULT",
    reference_id: extraction,
    label: `Text v2 분석 · ${extraction.slice(0, 8)}`,
  });
  return options;
}

function recommendedAllowDecision(packet: Record<string, unknown>): string | null {
  const effects = Array.isArray(packet.policy_effects) ? packet.policy_effects : [];
  const decisions = new Set<string>();
  effects.forEach((raw) => {
    const effect = objectValue(raw);
    if (text(effect?.type) !== "MARK_REVIEW_ELIGIBILITY") return;
    const mapped = eligibilityDecision[text(effect?.value) ?? ""];
    if (mapped) decisions.add(mapped);
  });
  return decisions.size === 1 ? [...decisions][0] ?? null : null;
}

export function assessQuickReview(detail: ReviewTaskDetail): QuickReviewAssessment {
  const basis = reviewBasisOptions(detail);
  const hasRule = basis.some((item) => item.type === "POLICY_RULE_RESULT");
  const hasCitation = basis.some((item) => item.type === "POLICY_CITATION");
  const summary = text(detail.packet.policy_summary_status ?? detail.packet.summary_status);
  const qualification = objectValue(detail.packet.qualification_snapshot)
    ?? objectValue(detail.packet.input_qualification);
  const allowDecision = recommendedAllowDecision(detail.packet);

  let score = 0;
  if (summary === "REQUIRES_HUMAN_REVIEW") score += 0.35;
  if (hasRule) score += 0.25;
  if (hasCitation) score += 0.15;
  if (qualification && Object.keys(qualification).length > 0) score += 0.1;
  if (allowDecision) score += 0.15;
  score = Math.round(score * 100) / 100;

  const blockers: string[] = [];
  if (summary !== "REQUIRES_HUMAN_REVIEW") blockers.push("추가 자료 요청 또는 정책 입력 확인이 먼저 필요합니다.");
  if (!hasRule && !hasCitation) blockers.push("고정된 정책 규칙 또는 인용 근거가 없습니다.");
  if (score < QUICK_REVIEW_READINESS_THRESHOLD) blockers.push("빠른 검토 준비도가 PoC 기준보다 낮습니다.");

  return {
    score,
    threshold: QUICK_REVIEW_READINESS_THRESHOLD,
    eligible: blockers.length === 0,
    allowDecision,
    allowLabel: allowDecision ? decisionLabels[allowDecision] ?? "허용 처리" : "허용 유형 확인 필요",
    basis,
    blockers,
  };
}

export function quickResolveInput(
  assessment: QuickReviewAssessment,
  verdict: QuickReviewVerdict,
  expectedVersion: number,
): ResolveInput {
  if (!assessment.eligible) throw new Error(assessment.blockers[0] ?? "빠른 검토를 진행할 수 없습니다.");
  if (verdict === "ALLOW" && !assessment.allowDecision) {
    throw new Error("정책 효과에서 허용 처리 유형을 하나로 확정할 수 없습니다.");
  }
  const policyBasis = [
    assessment.basis.find((item) => item.type === "POLICY_RULE_RESULT"),
    assessment.basis.find((item) => item.type === "POLICY_CITATION"),
  ].filter((item): item is BasisOption => item !== undefined);
  return {
    expected_version: expectedVersion,
    decision: verdict === "ALLOW" ? assessment.allowDecision as string : "REJECT_REQUEST",
    reason_codes: [verdict === "ALLOW" ? "POLICY_CONDITION_MET" : "POLICY_CONDITION_NOT_MET"],
    rationale: verdict === "ALLOW"
      ? "담당자가 고정된 정책 규칙과 인용 근거를 확인하고 요청 처리를 허용했습니다."
      : "담당자가 고정된 정책 규칙과 인용 근거를 확인하고 요청 처리를 허용하지 않았습니다.",
    basis: policyBasis.map(({ type, reference_id }) => ({ type, reference_id })),
  };
}
