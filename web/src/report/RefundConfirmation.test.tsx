import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ReviewReport } from "../api/contracts";
import { RefundConfirmation } from "./RefundConfirmation";
import { buildRefundDocument } from "./refundDocument";

const completeRefund: ReviewReport = {
  schema_version: "review_report/1.0.0",
  report_id: "96f0b4f6-a24a-4f0c-9965-613c4c15c428",
  case_id: "case-refund",
  resolution_id: "resolution-refund",
  resolution_version: 2,
  terminal_event_id: "event-refund",
  case_snapshot: { order_ref: "DEMO-V2-ORD-20260828-002", product_ref: "DEMO-V2-FLIPTOP-CONTAINER-02", requested_action: "REFUND", created_at: "2026-08-28T01:10:00Z", synthetic_commerce_context: {
    schema_version: "synthetic_commerce_context/1.0.0", data_classification: "SYNTHETIC_DEMO_ONLY",
    customer: { customer_id: "CUST-DEMO-100002", display_name: "김하늘", phone_masked: "010-****-4821", membership_tier: "GOLD" },
    order: { sales_channel: "CSight 마켓", seller_name: "CSight 리빙", ordered_at: "2026-08-26T01:14:00Z", product_display_name: "화이트랩 바디 로션 300", sku: "CS-DEMO-FLP-002", quantity: 1, unit_price: "18900", merchandise_amount: "18900", shipping_fee: "0", discount_amount: "0", paid_amount: "18900", currency: "KRW", payment_method_masked: "신용카드 **** 1042", payment_status: "PAID" },
    delivery: { shipping_address_ref: "DEMO-V2-ADDR-002", recipient: "김하늘", phone_masked: "010-****-4821", postal_code: "06236", address_line1: "서울특별시 데모구 시연로 41", address_line2: "가상아파트 203동 804호", carrier: "CSight 로지스", tracking_number_masked: "CSL-****-0202", delivered_at: "2026-08-27T05:22:00Z" },
  } },
  analysis_snapshot: { status: "SUCCEEDED" },
  policy_snapshot: { rule_set_id: "CSCC-DEFECT-OPS", rule_set_version: "2026.08-demo", as_of_date: "2026-08-28" },
  review_snapshot: { decision_type: "APPROVE_REFUND", rationale: "배송 직후 확인된 결합부 파손", decided_by: "reviewer-7", decided_at: "2026-08-28T01:18:00Z", decision_hash: "decision-hash", packet_hash: "packet-hash" },
  resolution_snapshot: { status: "ACTION_DRY_RUN_VALIDATED", missing_fields: [], invalid_fields: [], terminal_event_at: "2026-08-28T01:19:00Z" },
  dry_run_snapshot: { intent: { intent_id: "intent-1", action_type: "REFUND", amount: "18900", currency: "KRW", quantity: 1 }, result: { result_id: "result-1", outcome: "VALIDATED", side_effects_performed: false } },
  qualification_snapshot: { scope: "SYNTHETIC_DEMO" },
  data_scope: { real_customer_data: false },
  generated_at: "2026-08-28T01:20:00Z",
  content_hash: "report-hash",
};

describe("RefundConfirmation", () => {
  it("renders a complete refund like an operations document without claiming real execution", () => {
    render(<RefundConfirmation document={buildRefundDocument(completeRefund)} />);

    expect(screen.getByRole("heading", { name: "환불 처리 확인서" })).toBeVisible();
    expect(screen.getAllByText(/18,900/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("김하늘").length).toBeGreaterThan(0);
    expect(screen.getByText("CUST-100002")).toBeVisible();
    expect(screen.getByText(/서울특별시 한빛구/)).toBeVisible();
    expect(screen.getAllByText("환불 요청 검증 완료").length).toBeGreaterThan(0);
    expect(screen.getByText("미요청 · 외부 시스템 미연결")).toBeVisible();
    expect(screen.getByText("외부 결제사 전송 없음 · 실제 환불 미실행")).toBeVisible();
    expect(screen.getByText("실제 카드 승인 취소, 계좌 환급, 상품 회수 또는 고객 통지는 수행되지 않았습니다.")).toBeVisible();
  });
});
