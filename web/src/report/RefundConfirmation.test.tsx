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
  case_snapshot: { order_ref: "DEMO-V2-ORD-20260828-002", product_ref: "DEMO-V2-FLIPTOP-CONTAINER-02", requested_action: "REFUND", created_at: "2026-08-28T01:10:00Z" },
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
    expect(screen.getAllByText("환불 요청 검증 완료").length).toBeGreaterThan(0);
    expect(screen.getByText("미요청 · DRY-RUN")).toBeVisible();
    expect(screen.getByText("외부 결제사 전송 없음 · 실제 환불 미실행")).toBeVisible();
    expect(screen.getByText("실제 카드 승인 취소, 계좌 환급, 상품 회수 또는 고객 통지는 수행되지 않았습니다.")).toBeVisible();
  });
});
