import type { ReviewReport } from "../api/contracts";

type JsonRecord = Record<string, unknown>;

export type RefundDocumentStatus = "validated" | "needs-input" | "failed" | "pending";

export interface RefundDocumentModel {
  isRefund: boolean;
  documentNumber: string;
  orderRef: string;
  productRef: string;
  actionType: string;
  decisionType: string;
  resolutionStatus: string;
  status: RefundDocumentStatus;
  statusLabel: string;
  amountLabel: string;
  quantityLabel: string;
  refundMethodLabel: string;
  refundReason: string;
  requestedAt: string;
  approvedAt: string;
  validatedAt: string;
  reviewer: string;
  policyReference: string;
  policyAsOfDate: string;
  missingFields: string[];
  invalidFields: string[];
  intentId: string;
  resultId: string;
  resultOutcome: string;
  sideEffectsPerformed: boolean;
  reportId: string;
  reportHash: string;
  decisionHash: string;
  packetHash: string;
  generatedAt: string;
}

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function stringValue(source: JsonRecord, ...keys: string[]): string {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
  }
  return "";
}

function stringList(source: JsonRecord, key: string): string[] {
  const value = source[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item)) : [];
}

function refundStatus(value: string): Pick<RefundDocumentModel, "status" | "statusLabel"> {
  if (value === "ACTION_DRY_RUN_VALIDATED") return { status: "validated", statusLabel: "환불 요청 검증 완료" };
  if (value === "ACTION_NEEDS_INPUT") return { status: "needs-input", statusLabel: "환불 정보 보완 필요" };
  if (value === "ACTION_DRY_RUN_FAILED") return { status: "failed", statusLabel: "환불 요청 검증 실패" };
  return { status: "pending", statusLabel: "환불 검토 기록" };
}

function formatAmount(amount: string, currency: string): string {
  if (!amount || !currency) return "입력 필요";
  const numericAmount = Number(amount);
  if (!Number.isFinite(numericAmount)) return `${amount} ${currency}`;
  try {
    return new Intl.NumberFormat("ko-KR", { style: "currency", currency }).format(numericAmount);
  } catch {
    return `${numericAmount.toLocaleString("ko-KR")} ${currency}`;
  }
}

function policyReference(policy: JsonRecord): string {
  const name = stringValue(policy, "rule_set_id", "rule_set_name") || "정책 규칙 세트";
  const version = stringValue(policy, "rule_set_version");
  return version ? `${name} · v${version}` : name;
}

export function buildRefundDocument(report: ReviewReport): RefundDocumentModel {
  const caseSnapshot = record(report.case_snapshot);
  const review = record(report.review_snapshot);
  const resolution = record(report.resolution_snapshot);
  const policy = record(report.policy_snapshot);
  const dryRun = record(report.dry_run_snapshot);
  const intent = record(dryRun.intent ?? dryRun);
  const result = record(dryRun.result ?? dryRun);
  const actionType = stringValue(intent, "action_type") || (stringValue(caseSnapshot, "requested_action") === "REFUND" ? "REFUND" : "");
  const decisionType = stringValue(review, "decision_type", "decision");
  const resolutionStatus = stringValue(resolution, "status");
  const amount = stringValue(intent, "amount");
  const currency = stringValue(intent, "currency");
  const quantity = stringValue(intent, "quantity");
  const reportSuffix = report.report_id.replace(/[^a-zA-Z0-9]/g, "").slice(0, 12).toUpperCase() || "UNASSIGNED";

  return {
    isRefund: actionType === "REFUND" || decisionType === "APPROVE_REFUND",
    documentNumber: `CS-RF-${reportSuffix}`,
    orderRef: stringValue(caseSnapshot, "order_ref") || "주문번호 미기록",
    productRef: stringValue(caseSnapshot, "product_ref") || "상품번호 미기록",
    actionType: actionType || "REFUND",
    decisionType: decisionType || "결정 유형 미기록",
    resolutionStatus,
    ...refundStatus(resolutionStatus),
    amountLabel: formatAmount(amount, currency),
    quantityLabel: quantity ? `${quantity}개` : "수량 미기록",
    refundMethodLabel: "원결제수단 환급 예정 · 외부 연동 시 확정",
    refundReason: stringValue(review, "rationale") || "담당자 승인 근거는 고정 스냅샷을 확인하세요.",
    requestedAt: stringValue(caseSnapshot, "created_at"),
    approvedAt: stringValue(review, "decided_at", "resolved_at"),
    validatedAt: stringValue(resolution, "terminal_event_at") || report.generated_at,
    reviewer: stringValue(review, "decided_by", "actor_id", "actor_type") || "인증된 담당자",
    policyReference: policyReference(policy),
    policyAsOfDate: stringValue(policy, "as_of_date") || "기준일 미기록",
    missingFields: stringList(resolution, "missing_fields"),
    invalidFields: stringList(resolution, "invalid_fields"),
    intentId: stringValue(intent, "intent_id") || "미생성",
    resultId: stringValue(result, "result_id") || "미생성",
    resultOutcome: stringValue(result, "outcome") || "시뮬레이션 미수행",
    sideEffectsPerformed: result.side_effects_performed === true || dryRun.side_effects_performed === true,
    reportId: report.report_id,
    reportHash: report.content_hash,
    decisionHash: stringValue(review, "decision_hash") || "미기록",
    packetHash: stringValue(review, "packet_hash") || "미기록",
    generatedAt: report.generated_at,
  };
}
