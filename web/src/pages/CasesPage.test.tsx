import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { tokenVault } from "../auth/tokenVault";
import * as AuthProvider from "../auth/AuthProvider";
import { server } from "../test/server";
import { CasesPage } from "./CasesPage";

const now = "2026-08-29T00:00:00Z";
const counts = { all: 2, my: 1, unassigned: 1, urgent: 1, waiting_evidence: 0, complete: 0 };

function item(caseId: string, overrides: Record<string, unknown> = {}) {
  return {
    case_id: caseId,
    case_status: "OPEN",
    order_ref: `ORD-${caseId}`,
    product_ref: "DEMO-COMPACT-CASE-10",
    requested_action: "REFUND",
    created_at: now,
    updated_at: now,
    assignment_version: 0,
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><CasesPage /></MemoryRouter></QueryClientProvider>);
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  tokenVault.clear();
  vi.restoreAllMocks();
});
afterAll(() => server.close());

describe("CasesPage operator queue", () => {
  it("renders counts and fail-soft rows from exactly one initial queue request without detail fan-out", async () => {
    let queueRequests = 0;
    let detailRequests = 0;
    server.use(
      http.get("/api/v1/operator/cases", () => {
        queueRequests += 1;
        return HttpResponse.json({ items: [
          item("case-1", { assignee_id: "reviewer-1", review_status: "CLAIMED", review_priority: "HIGH", resolution_status: null, report_id: null, report_generated_at: null, review_task_id: "task-1" }),
          item("case-2", { case_status: "FUTURE_CASE_STATE", product_ref: "SKU-FUTURE", requested_action: "FUTURE_ACTION" }),
        ], counts, next_cursor: null });
      }),
      http.get("/api/v1/cases/:caseId", () => {
        detailRequests += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
    );
    tokenVault.set("test-token", 600);

    renderPage();

    expect(await screen.findByText("플랫케이스 오거나이저 2P")).toBeVisible();
    expect(screen.getByText("SKU-FUTURE 상품")).toBeVisible();
    expect(screen.getByText("FUTURE_CASE_STATE")).toBeVisible();
    expect(screen.getAllByText("미배정").length).toBeGreaterThan(0);
    expect(screen.getByRole("tab", { name: /전체/ })).toHaveTextContent("2");
    expect(screen.getByRole("tab", { name: /긴급/ })).toHaveTextContent("1");
    expect(screen.getByText("reviewer-1")).toBeVisible();
    expect(screen.getAllByText(/대기/).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /새 문의|첫 문의/ })).not.toBeInTheDocument();
    await waitFor(() => expect(queueRequests).toBe(1));
    expect(detailRequests).toBe(0);
  });

  it("searches the complete queue on the server by order, product, or case reference", async () => {
    const requests: URL[] = [];
    server.use(http.get("/api/v1/operator/cases", ({ request }) => {
      const url = new URL(request.url);
      requests.push(url);
      const searching = url.searchParams.get("q") === "ORD-ALPHA";
      return HttpResponse.json({
        items: searching
          ? [item("case-alpha", { order_ref: "ORD-ALPHA", product_ref: "DEMO-COMPACT-CASE-10" })]
          : [
            item("case-alpha", { order_ref: "ORD-ALPHA", product_ref: "DEMO-COMPACT-CASE-10" }),
            item("case-beta", { order_ref: "ORD-BETA", product_ref: "SKU-BETA" }),
          ],
        counts: searching ? { ...counts, all: 1 } : counts,
        next_cursor: null,
      });
    }));
    tokenVault.set("test-token", 600);
    renderPage();
    const user = userEvent.setup();

    expect(await screen.findByText("SKU-BETA 상품")).toBeVisible();
    await user.type(screen.getByPlaceholderText("주문·상품·문의 번호 검색"), "ORD-ALPHA");

    await waitFor(() => expect(requests.some((request) => request.searchParams.get("q") === "ORD-ALPHA")).toBe(true));
    expect(screen.getByText("플랫케이스 오거나이저 2P")).toBeVisible();
    expect(screen.queryByText("SKU-BETA 상품")).not.toBeInTheDocument();
    expect(screen.getByText("검색 결과 1건")).toBeVisible();
  });

  it("appends an opaque cursor page while keeping the first page visible", async () => {
    const requests: string[] = [];
    server.use(http.get("/api/v1/operator/cases", ({ request }) => {
      const url = new URL(request.url);
      requests.push(url.search);
      const cursor = url.searchParams.get("cursor");
      return HttpResponse.json(cursor
        ? { items: [item("case-2", { product_ref: "SKU-SECOND" })], counts, next_cursor: null }
        : { items: [item("case-1")], counts, next_cursor: "opaque-cursor-2" });
    }));
    tokenVault.set("test-token", 600);
    renderPage();
    const user = userEvent.setup();

    expect(await screen.findByText("주문 번호 ORD-case-1", { exact: false })).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0]).toContain("view=all");
    expect(requests[0]).toContain("sort=newest");
    await user.click(screen.getByRole("button", { name: "문의 더 보기" }));

    expect(await screen.findByText("SKU-SECOND 상품")).toBeVisible();
    expect(screen.getByText("주문 번호 ORD-case-1", { exact: false })).toBeVisible();
    expect(requests).toHaveLength(2);
    expect(requests[1]).toContain("cursor=opaque-cursor-2");
  });

  it("supports arrow-key view changes and sends the selected view and sort", async () => {
    const requests: URL[] = [];
    server.use(http.get("/api/v1/operator/cases", ({ request }) => {
      requests.push(new URL(request.url));
      return HttpResponse.json({ items: [], counts, next_cursor: null });
    }));
    tokenVault.set("test-token", 600);
    renderPage();
    const user = userEvent.setup();

    const all = await screen.findByRole("tab", { name: /전체/ });
    all.focus();
    await user.keyboard("{ArrowRight}");
    await waitFor(() => expect(requests.some((request) => request.searchParams.get("view") === "my")).toBe(true));
    expect(screen.getByRole("tab", { name: /내 업무/ })).toHaveAttribute("aria-selected", "true");

    await user.selectOptions(screen.getByLabelText("문의 정렬"), "oldest");
    await waitFor(() => expect(requests.some((request) => request.searchParams.get("view") === "my" && request.searchParams.get("sort") === "oldest")).toBe(true));
  });

  it("locks a reviewer account to assigned waiting inquiries", async () => {
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
    server.use(http.get("/api/v1/operator/cases", ({ request }) => {
      requests.push(new URL(request.url));
      return HttpResponse.json({
        items: [item("case-owned", { assignee_id: "reviewer-1", assignment_version: 2 })],
        counts: { ...counts, my: 1 },
        next_cursor: null,
      });
    }));

    renderPage();

    expect(await screen.findByRole("heading", { name: "문의 대기" })).toBeVisible();
    expect(screen.getByRole("tab", { name: /내 업무/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("tab", { name: /전체/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /문의 담당자/ })).not.toBeInTheDocument();
    await waitFor(() => expect(requests[0]?.searchParams.get("view")).toBe("my"));
  });
});
