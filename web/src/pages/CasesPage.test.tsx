import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { tokenVault } from "../auth/tokenVault";
import { server } from "../test/server";
import { CasesPage, shouldDisplayCaseOnDesk } from "./CasesPage";

const now = "2026-08-28T00:00:00Z";

function summary(caseId: string, orderRef: string) {
  return {
    case_id: caseId,
    tenant_id: "tenant-1",
    domain_type: "product_defect_cs",
    status: "OPEN",
    order_ref: orderRef,
    product_ref: `SKU-${caseId}`,
    requested_action: "EXCHANGE",
    created_at: now,
    updated_at: now,
  };
}

const v2Base = {
  schema_version: "2.0",
  dataset_id: "realistic-internal-demo-v2",
  scenario_scope: "INTERNAL_CURATED_ECOMMERCE_INQUIRY_6_DEFECT_4_BELOW_THRESHOLD",
};

const v3Base = {
  schema_version: "3.0",
  dataset_id: "realistic-internal-demo-v3",
  scenario_scope: "INTERNAL_CURATED_ECOMMERCE_EXPANSION_12_DEFECT_8_REFERENCE_TOTAL",
};

const commerceContext = {
  schema_version: "synthetic_commerce_context/1.0.0", data_classification: "SYNTHETIC_DEMO_ONLY",
  customer: { customer_id: "CUST-DEMO-100003", display_name: "이도윤", phone_masked: "010-****-7356", membership_tier: "VIP" },
  order: { sales_channel: "CSight 마켓", seller_name: "CSight 퍼스널케어", ordered_at: "2026-08-18T12:05:00Z", product_display_name: "바이올렛 리페어 에센스 100", sku: "CS-DEMO-SPR-003", quantity: 1, unit_price: "27900", merchandise_amount: "27900", shipping_fee: "0", discount_amount: "2000", paid_amount: "25900", currency: "KRW", payment_method_masked: "체크카드 **** 7731", payment_status: "PAID" },
  delivery: { shipping_address_ref: "DEMO-V2-ADDR-003", recipient: "이도윤", phone_masked: "010-****-7356", postal_code: "13529", address_line1: "경기도 가상시 데모로 103", address_line2: "시연빌라 502호", carrier: "CSight 익스프레스", tracking_number_masked: "CSE-****-0303", delivered_at: "2026-08-19T07:48:00Z" },
};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  tokenVault.clear();
});
afterAll(() => server.close());

describe("CasesPage demo revision filter", () => {
  it("keeps general and v1 cases while exposing only the current v2 revision", async () => {
    const items = [
      summary("general", "ORD-GENERAL"),
      summary("v1", "ORD-V1"),
      summary("legacy-v2", "ORD-LEGACY-V2"),
      { ...summary("r1-v2", "ORD-R1-V2"), product_ref: "DEMO-V2-SPRAY-CONTAINER-03" },
      { ...summary("r2-v2", "ORD-R2-V2"), product_ref: "DEMO-V2-SPRAY-CONTAINER-03" },
    ];
    const attributesByCase: Record<string, Record<string, unknown>> = {
      general: {},
      v1: { realistic_demo: { schema_version: "1.0", dataset_id: "realistic-internal-demo-v1" } },
      "legacy-v2": { realistic_demo: v2Base },
      "r1-v2": { realistic_demo: { ...v2Base, narrative_revision: "VISUAL_ALIGNED_R1" } },
      "r2-v2": { realistic_demo: { ...v2Base, narrative_revision: "COMMERCE_CONTEXT_R2_E3" }, synthetic_commerce_context: commerceContext },
    };
    server.use(
      http.get("/api/v1/cases", () => HttpResponse.json({ items, page: 1, page_size: 100, total: items.length })),
      http.get("/api/v1/cases/:caseId", ({ params }) => {
        const item = items.find((candidate) => candidate.case_id === params.caseId)!;
        return HttpResponse.json({
          ...item,
          customer_message: "문의 내용",
          attributes: attributesByCase[item.case_id],
          created_by: "user-1",
          evidence: [],
          status_history: [],
          latest_analysis_run: null,
        });
      }),
    );
    tokenVault.set("test-token", 600);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter><CasesPage /></MemoryRouter></QueryClientProvider>);

    expect(await screen.findByText("주문 번호 ORD-GENERAL")).toBeVisible();
    expect(screen.getByText("주문 번호 ORD-V1")).toBeVisible();
    expect(screen.getByText("SKU-general 상품")).toBeVisible();
    expect(screen.queryByText("등록 상품 문의")).not.toBeInTheDocument();
    expect(screen.queryByText(/ORD-R1-V2/)).not.toBeInTheDocument();
    expect(screen.getByText(/ORD-R2-V2/)).toBeVisible();
    expect(screen.getByText("바이올렛 리페어 에센스 100")).toBeVisible();
    expect(screen.getByText("상품 번호 CS-SPR-003 · 가격대 21,000~35,000원")).toBeVisible();
    expect(screen.getAllByText("교환").length).toBeGreaterThan(0);
    expect(screen.queryByText("EXCHANGE")).not.toBeInTheDocument();
    expect(screen.getByText(/이도윤 · CUST-100003 · 결제/)).toHaveTextContent("25,900");
    expect(screen.queryByText("ORD-LEGACY-V2")).not.toBeInTheDocument();
    expect(screen.getByText("3건")).toBeVisible();
  });

  it("fails closed for missing or non-R1 v2 narrative revisions", () => {
    expect(shouldDisplayCaseOnDesk({ realistic_demo: v2Base })).toBe(false);
    expect(shouldDisplayCaseOnDesk({ realistic_demo: { ...v2Base, narrative_revision: "LEGACY_R0" } })).toBe(false);
    expect(shouldDisplayCaseOnDesk({ realistic_demo: { ...v2Base, narrative_revision: "VISUAL_ALIGNED_R1" } })).toBe(false);
    expect(shouldDisplayCaseOnDesk({ realistic_demo: { ...v2Base, narrative_revision: "COMMERCE_CONTEXT_R2" } })).toBe(false);
    expect(shouldDisplayCaseOnDesk({ realistic_demo: { ...v2Base, narrative_revision: "COMMERCE_CONTEXT_R2_E3" } })).toBe(true);
    expect(shouldDisplayCaseOnDesk({})).toBe(true);
  });

  it("shows only the approved v3 expansion revision", () => {
    expect(shouldDisplayCaseOnDesk({ realistic_demo: v3Base })).toBe(false);
    expect(shouldDisplayCaseOnDesk({ realistic_demo: { ...v3Base, narrative_revision: "CLOSED_SET_EXPANSION_R3" } })).toBe(true);
    expect(shouldDisplayCaseOnDesk({ realistic_demo: { ...v3Base, narrative_revision: "UNREVIEWED_R4" } })).toBe(false);
  });
});
