import { describe, expect, it } from "vitest";

import type { ReviewReport } from "../api/contracts";
import { buildRefundDocument } from "./refundDocument";

const commerceContext = {
  schema_version: "synthetic_commerce_context/1.0.0",
  data_classification: "SYNTHETIC_DEMO_ONLY",
  customer: { customer_id: "CUST-DEMO-100002", display_name: "김하늘", phone_masked: "010-****-4821", membership_tier: "GOLD" },
  order: { sales_channel: "CSight 마켓", seller_name: "CSight 리빙", ordered_at: "2026-08-26T01:14:00Z", product_display_name: "화이트랩 바디 로션 300", sku: "CS-DEMO-FLP-002", quantity: 1, unit_price: "18900", merchandise_amount: "18900", shipping_fee: "0", discount_amount: "0", paid_amount: "18900", currency: "KRW", payment_method_masked: "신용카드 **** 1042", payment_status: "PAID" },
  delivery: { shipping_address_ref: "DEMO-V2-ADDR-002", recipient: "김하늘", phone_masked: "010-****-4821", postal_code: "06236", address_line1: "서울특별시 데모구 시연로 41", address_line2: "가상아파트 203동 804호", carrier: "CSight 로지스", tracking_number_masked: "CSL-****-0202", delivered_at: "2026-08-27T05:22:00Z" },
};

function report(overrides: Partial<ReviewReport> = {}): ReviewReport {
  return {
    schema_version: "review_report/1.0.0",
    report_id: "96f0b4f6-a24a-4f0c-9965-613c4c15c428",
    case_id: "case-1",
    resolution_id: "resolution-1",
    resolution_version: 2,
    terminal_event_id: "event-1",
    case_snapshot: { order_ref: "ORD-20260828-1042", product_ref: "TB-900-IV", requested_action: "REFUND", created_at: "2026-08-28T01:10:00Z", synthetic_commerce_context: commerceContext },
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
    expect(document.paidAmountLabel).toContain("18,900");
    expect(document.customerName).toBe("김하늘");
    expect(document.shippingAddress).toContain("한빛구");
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
