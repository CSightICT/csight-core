import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { tokenVault } from "../auth/tokenVault";
import * as AuthProvider from "../auth/AuthProvider";
import { server } from "../test/server";
import { ReviewsPage } from "./ReviewsPage";

const now = "2026-08-29T00:00:00Z";
const counts = { all: 2, my: 0, unassigned: 2, urgent: 1, waiting_evidence: 1, complete: 0 };

function item(taskId: string, overrides: Record<string, unknown> = {}) {
  return {
    review_task_id: taskId,
    case_id: `case-${taskId}`,
    case_status: "REVIEW_PENDING",
    order_ref: `ORD-${taskId}`,
    product_ref: "DEMO-COMPACT-CASE-10",
    requested_action: "REFUND",
    inquiry_preview: `문의 내용 ${taskId}`,
    task_type: "STANDARD_REVIEW",
    priority: "NORMAL",
    status: "PENDING",
    version: 1,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><ReviewsPage /></MemoryRouter></QueryClientProvider>);
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  tokenVault.clear();
  vi.restoreAllMocks();
});
afterAll(() => server.close());

describe("ReviewsPage operator queue", () => {
  it("renders all rows from one projection request even when optional fields are missing or status is unknown", async () => {
    let queueRequests = 0;
    let caseRequests = 0;
    server.use(
      http.get("/api/v1/operator/reviews", () => {
        queueRequests += 1;
        return HttpResponse.json({ items: [
          item("task-1", { assignee_id: "reviewer-1", priority: "HIGH", resolution_status: null, report_id: null, report_generated_at: null }),
          item("task-2", { status: "FUTURE_REVIEW_STATE", product_ref: "SKU-UNKNOWN" }),
        ], counts, next_cursor: null });
      }),
      http.get("/api/v1/cases/:caseId", () => {
        caseRequests += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
    );
    tokenVault.set("test-token", 600);

    renderPage();

    expect(await screen.findByText("문의 내용 task-1")).toBeVisible();
    expect(screen.getByText("문의 내용 task-2")).toBeVisible();
    expect(screen.getByText("FUTURE_REVIEW_STATE")).toBeVisible();


    expect(screen.getByRole("tab", { name: /증거 대기/ })).toHaveTextContent("1");
    expect(screen.getAllByText(/대기/).length).toBeGreaterThan(0);
    await waitFor(() => expect(queueRequests).toBe(1));
    expect(caseRequests).toBe(0);
  });

  it("supports cursor pagination without replacing already loaded review tasks", async () => {
    const requests: string[] = [];
    server.use(http.get("/api/v1/operator/reviews", ({ request }) => {
      const url = new URL(request.url);
      requests.push(url.search);
      return HttpResponse.json(url.searchParams.has("cursor")
        ? { items: [item("task-2", { product_ref: "SKU-SECOND-REVIEW" })], counts, next_cursor: null }
        : { items: [item("task-1")], counts, next_cursor: "review-cursor-2" });
    }));
    tokenVault.set("test-token", 600);
    renderPage();
    const user = userEvent.setup();

    expect(await screen.findByText(/문의 내용 task-1/)).toBeVisible();
    expect(requests).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "검토 작업 더 보기" }));

    expect(await screen.findByText("문의 내용 task-2")).toBeVisible();
    expect(screen.getByText(/문의 내용 task-1/)).toBeVisible();
    expect(requests).toHaveLength(2);
    expect(requests[1]).toContain("cursor=review-cursor-2");
  });

  it("searches the complete review queue on the server by order, product, or case reference", async () => {
    const requests: URL[] = [];
    server.use(http.get("/api/v1/operator/reviews", ({ request }) => {
      const url = new URL(request.url);
      requests.push(url);
      const searching = url.searchParams.get("q") === "case-task-alpha";
      return HttpResponse.json({
        items: searching
          ? [item("task-alpha", { order_ref: "ORD-ALPHA", product_ref: "DEMO-COMPACT-CASE-10" })]
          : [
            item("task-alpha", { order_ref: "ORD-ALPHA", product_ref: "DEMO-COMPACT-CASE-10" }),
            item("task-beta", { order_ref: "ORD-BETA", product_ref: "SKU-BETA" }),
          ],
        counts: searching ? { ...counts, all: 1 } : counts,
        next_cursor: null,
      });
    }));
    tokenVault.set("test-token", 600);
    renderPage();
    const user = userEvent.setup();

    expect(await screen.findByText("문의 내용 task-beta")).toBeVisible();
    await user.type(screen.getByPlaceholderText("주문·상품·문의 번호 검색"), "case-task-alpha");

    await waitFor(() => expect(requests.some((request) => request.searchParams.get("q") === "case-task-alpha")).toBe(true));
    expect(screen.getByText("문의 내용 task-alpha")).toBeVisible();
    expect(screen.queryByText("문의 내용 task-beta")).not.toBeInTheDocument();
    expect(screen.getByText("검색 결과 1건")).toBeVisible();
  });

  it("shows only inquiries completed by the signed-in reviewer", async () => {
    const requests: URL[] = [];
    vi.spyOn(AuthProvider, "useOptionalAuth").mockReturnValue({
      user: { user_id: "reviewer-1", tenant_id: "tenant-1", email: "reviewer@test.local", display_name: "담당자", roles: ["REVIEWER"] },
      busy: false,
      sessionExpired: false,
      sessionExpiresWithinFiveMinutes: false,
      oidcAvailable: false,
      legacyPasswordAvailable: true,
      login: vi.fn(async () => undefined),
      startOidcLogin: vi.fn(),
      logout: vi.fn(async () => undefined),
      hasRole: (role: string) => role === "REVIEWER",
    });
    server.use(http.get("/api/v1/operator/reviews", ({ request }) => {
      requests.push(new URL(request.url));
      return HttpResponse.json({
        items: [item("task-complete", { status: "RESOLVED", assignee_id: null })],
        counts: { ...counts, complete: 1 },
        next_cursor: null,
      });
    }));

    renderPage();

    expect(await screen.findByRole("heading", { name: "내 문의 처리 현황" })).toBeVisible();
    expect(screen.getByRole("tab", { name: /완료/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("tab", { name: /전체/ })).not.toBeInTheDocument();
    await waitFor(() => expect(requests[0]?.searchParams.get("view")).toBe("complete"));
  });
});
