import { describe, expect, it } from "vitest";

import { formatCommerceMoney, readSyntheticCommerceContext } from "./syntheticCommerceContext";

const context = {
  schema_version: "synthetic_commerce_context/1.0.0",
  data_classification: "SYNTHETIC_DEMO_ONLY",
  customer: { customer_id: "CUST-DEMO-100002", display_name: "김하늘", phone_masked: "010-****-4821", membership_tier: "GOLD" },
  order: {
    sales_channel: "CSight 마켓", seller_name: "CSight 리빙", ordered_at: "2026-08-25T01:14:00Z",
    product_display_name: "화이트랩 바디 로션 300", sku: "CS-DEMO-FLP-002", quantity: 1,
    unit_price: "18900", merchandise_amount: "18900", shipping_fee: "0", discount_amount: "0",
    paid_amount: "18900", currency: "KRW", payment_method_masked: "신한카드 **** 1042", payment_status: "PAID",
  },
  delivery: {
    shipping_address_ref: "DEMO-V2-ADDR-002", recipient: "김하늘", phone_masked: "010-****-4821",
    postal_code: "06236", address_line1: "서울특별시 데모구 시연로 28", address_line2: "CSight 타워 101호",
    carrier: "CSight 로지스", tracking_number_masked: "CSL-****-0202", delivered_at: "2026-08-27T05:22:00Z",
  },
};

describe("synthetic commerce context", () => {
  it("decodes the reserved Case attribute and formats money", () => {
    const decoded = readSyntheticCommerceContext({ synthetic_commerce_context: context });
    expect(decoded?.customer.displayName).toBe("김하늘");
    expect(decoded?.order.paidAmount).toBe("18900");
    expect(decoded?.delivery.addressLine1).toContain("한빛구");
    expect(formatCommerceMoney("18900", "KRW")).toContain("18,900");
  });

  it("fails closed for an unsupported or incomplete snapshot", () => {
    expect(readSyntheticCommerceContext({ ...context, data_classification: "REAL" })).toBeNull();
    expect(readSyntheticCommerceContext({ ...context, customer: {} })).toBeNull();
  });
});
