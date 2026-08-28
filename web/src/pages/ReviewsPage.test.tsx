import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { tokenVault } from "../auth/tokenVault";
import { server } from "../test/server";
import { ReviewsPage } from "./ReviewsPage";

const now = "2026-08-28T00:00:00Z";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  tokenVault.clear();
});
afterAll(() => server.close());

describe("ReviewsPage", () => {
  it("uses the same Korean product name as the inquiry desk", async () => {
    server.use(
      http.get("/api/v1/human-review-tasks", () => HttpResponse.json({ items: [{
        id: "review-1",
        case_id: "case-1",
        policy_evaluation_run_id: "policy-1",
        task_type: "STANDARD_REVIEW",
        priority: "NORMAL",
        status: "PENDING",
        current_assignee_id: null,
        version: 1,
        mapping_rule_name: "standard",
        mapping_rule_version: "1.0.0",
        created_at: now,
        updated_at: now,
        resolved_at: null,
      }] })),
      http.get("/api/v1/cases/case-1", () => HttpResponse.json({
        case_id: "case-1",
        tenant_id: "tenant-1",
        domain_type: "product_defect_cs",
        status: "REVIEW_PENDING",
        order_ref: "ORD-1",
        product_ref: "DEMO-COMPACT-CASE-10",
        requested_action: "REFUND",
        customer_message: "상품 상태를 확인해 주세요.",
        attributes: {},
        created_by: "user-1",
        created_at: now,
        updated_at: now,
        evidence: [],
        status_history: [],
        latest_analysis_run: null,
      })),
    );
    tokenVault.set("test-token", 600);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter><ReviewsPage /></MemoryRouter></QueryClientProvider>);

    expect(await screen.findByText("플랫케이스 오거나이저 2P")).toBeVisible();
    expect(screen.getByText(/일반 정책 검토 · 문의 번호/)).toBeVisible();
    expect(screen.queryByText("등록 상품 문의")).not.toBeInTheDocument();
  });
});
