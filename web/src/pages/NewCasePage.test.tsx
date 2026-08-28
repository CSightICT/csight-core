import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { tokenVault } from "../auth/tokenVault";
import { server } from "../test/server";
import { NewCasePage } from "./NewCasePage";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("NewCasePage", () => {
  it("sends the exact REFUND external_action_input without inference or extras", async () => {
    let captured: unknown;
    server.use(http.post("/api/v1/cases", async ({ request }) => {
      captured = await request.json();
      return HttpResponse.json({ case_id: "case-refund", status: "OPEN", created_at: "2026-08-27T00:00:00Z" });
    }));
    tokenVault.set("test-token", 600);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/cases/new"]}><Routes><Route path="/cases/new" element={<NewCasePage />} /><Route path="/cases/:caseId" element={<p>생성 완료</p>} /></Routes></MemoryRouter></QueryClientProvider>);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("주문 참조"), "ORD-1");
    await user.type(screen.getByLabelText("상품 참조"), "SKU-1");
    await user.type(screen.getByLabelText("고객 문의"), "제품이 파손되어 환불을 요청합니다.");
    await user.selectOptions(screen.getByLabelText("요청 유형"), "REFUND");
    await user.type(screen.getByLabelText("환불 금액"), "999999999999999.0001");
    await user.type(screen.getByLabelText("통화 코드"), "KRW");
    await user.click(screen.getByRole("button", { name: /문의 등록/ }));
    await screen.findByText("생성 완료");
    expect(captured).toEqual({
      order_ref: "ORD-1", product_ref: "SKU-1", customer_message: "제품이 파손되어 환불을 요청합니다.",
      requested_action: "REFUND", attributes: { external_action_input: { amount: "999999999999999.0001", currency: "KRW" } },
    });
    expect(JSON.stringify(captured)).not.toContain("refund_amount");
    await waitFor(() => expect(sessionStorage.length).toBe(0));
  });
});
