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

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  tokenVault.clear();
});
afterAll(() => server.close());

describe("CasesPage demo revision filter", () => {
  it("keeps general and v1 cases while only exposing VISUAL_ALIGNED_R1 v2 cases", async () => {
    const items = [
      summary("general", "ORD-GENERAL"),
      summary("v1", "ORD-V1"),
      summary("legacy-v2", "ORD-LEGACY-V2"),
      summary("r1-v2", "ORD-R1-V2"),
    ];
    const attributesByCase: Record<string, Record<string, unknown>> = {
      general: {},
      v1: { realistic_demo: { schema_version: "1.0", dataset_id: "realistic-internal-demo-v1" } },
      "legacy-v2": { realistic_demo: v2Base },
      "r1-v2": { realistic_demo: { ...v2Base, narrative_revision: "VISUAL_ALIGNED_R1" } },
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

    expect(await screen.findByText("ORD-GENERAL")).toBeVisible();
    expect(screen.getByText("ORD-V1")).toBeVisible();
    expect(screen.getByText("ORD-R1-V2")).toBeVisible();
    expect(screen.queryByText("ORD-LEGACY-V2")).not.toBeInTheDocument();
    expect(screen.getByText("3건")).toBeVisible();
  });

  it("fails closed for missing or non-R1 v2 narrative revisions", () => {
    expect(shouldDisplayCaseOnDesk({ realistic_demo: v2Base })).toBe(false);
    expect(shouldDisplayCaseOnDesk({ realistic_demo: { ...v2Base, narrative_revision: "LEGACY_R0" } })).toBe(false);
    expect(shouldDisplayCaseOnDesk({ realistic_demo: { ...v2Base, narrative_revision: "VISUAL_ALIGNED_R1" } })).toBe(true);
    expect(shouldDisplayCaseOnDesk({})).toBe(true);
  });
});
