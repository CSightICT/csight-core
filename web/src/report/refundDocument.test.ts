import { describe, expect, it } from "vitest";

import type { ReviewReport } from "../api/contracts";
import { buildRefundDocument } from "./refundDocument";

function report(overrides: Partial<ReviewReport> = {}): ReviewReport {
  return {
    schema_version: "review_report/1.0.0",
    report_id: "96f0b4f6-a24a-4f0c-9965-613c4c15c428",
    case_id: "case-1",
    resolution_id: "resolution-1",
    resolution_version: 2,
    terminal_event_id: "event-1",
    case_snapshot: { order_ref: "ORD-20260828-1042", product_ref: "TB-900-IV", requested_action: "REFUND", created_at: "2026-08-28T01:10:00Z" },
    analysis_snapshot: {},
    policy_snapshot: { rule_set_id: "csight-commerce-defect", rule_set_version: "2026.08-demo", as_of_date: "2026-08-28" },
    review_snapshot: { decision_type: "APPROVE_REFUND", rationale: "배송 직후 확인된 결합부 파손", decided_by: "reviewer-7", decided_at: "2026-08-28T01:18:00Z", decision_hash: "decision-hash", packet_hash: "packet-hash" },
    resolution_snapshot: { status: "ACTION_DRY_RUN_VALIDATED", missing_fields: [], invalid_fields: [], terminal_event_at: "2026-08-28T01:19:00Z" },
    dry_run_snapshot: { intent: { intent_id: "intent-1", action_type: "REFUND", amount: "18900", currency: "KRW", quantity: 1 }, result: { result_id: "result-1", outcome: "VALIDATED", side_effects_performed: false } },
    qualification_snapshot: {},
    data_scope: {},
    generated_at: "2026-08-28T01:20:00Z",
    content_hash: "report-hash",
    ...overrides,
  };
}

describe("buildRefundDocument", () => {
  it("maps an immutable refund snapshot to a printable processing confirmation", () => {
    const document = buildRefundDocument(report());

    expect(document.isRefund).toBe(true);
    expect(document.statusLabel).toBe("환불 요청 검증 완료");
    expect(document.amountLabel).toContain("18,900");
    expect(document.amountLabel).toContain("₩");
    expect(document.quantityLabel).toBe("1개");
    expect(document.sideEffectsPerformed).toBe(false);
    expect(document.documentNumber).toBe("CS-RF-96F0B4F6A24A");
  });

  it("does not infer missing refund parameters or claim execution", () => {
    const document = buildRefundDocument(report({
      resolution_snapshot: { status: "ACTION_NEEDS_INPUT", missing_fields: ["amount", "currency"], invalid_fields: [] },
      dry_run_snapshot: { intent: null, result: null },
    }));

    expect(document.statusLabel).toBe("환불 정보 보완 필요");
    expect(document.amountLabel).toBe("입력 필요");
    expect(document.missingFields).toEqual(["amount", "currency"]);
    expect(document.intentId).toBe("미생성");
    expect(document.resultId).toBe("미생성");
    expect(document.sideEffectsPerformed).toBe(false);
  });

  it("keeps non-refund reports on the generic report path", () => {
    const document = buildRefundDocument(report({
      case_snapshot: { requested_action: "REPAIR" },
      review_snapshot: { decision_type: "APPROVE_REPAIR" },
      dry_run_snapshot: { intent: { action_type: "REPAIR" }, result: null },
    }));

    expect(document.isRefund).toBe(false);
  });
});
