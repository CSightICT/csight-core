import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { CustomerCommunicationSimulation } from "../api/contracts";
import { CommunicationSimulationPanel } from "./CommunicationSimulationPanel";

const simulation: CustomerCommunicationSimulation = {
  schema_version: "customer_communication_simulation/1.0.0",
  communication_id: "communication-1",
  case_id: "case-1",
  review_report_id: "report-1",
  channel: "EMAIL",
  template_name: "customer_outcome_email",
  template_version: "1.0.0",
  recipient_label: "김하늘 고객님 · 010-****-4821",
  subject: "[CSight 데모] 환불 승인 안내",
  body: "18,900원 환불 승인으로 처리되었습니다.\n본 화면은 PoC용 메일 발송 시뮬레이션입니다.",
  delivery_status: "SIMULATED_NOT_SENT",
  side_effects_performed: false,
  created_at: "2026-08-28T01:00:00Z",
  content_hash: "a".repeat(64),
};

afterEach(() => vi.restoreAllMocks());

describe("CommunicationSimulationPanel", () => {
  it("creates a persisted preview while clearly showing that nothing was sent", async () => {
    vi.spyOn(api, "listCustomerCommunications").mockResolvedValue([]);
    vi.spyOn(api, "createCustomerCommunication").mockResolvedValue(simulation);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CommunicationSimulationPanel caseId="case-1" /></QueryClientProvider>);
    await userEvent.click(await screen.findByRole("button", { name: "안내 메일 만들기" }));
    expect(await screen.findByRole("dialog", { name: "고객 안내 메일 미리보기" })).toBeInTheDocument();
    expect(screen.getByText("[CSight] 환불 승인 안내")).toBeInTheDocument();
    expect(screen.getByText(/외부 메일 시스템에 전송되지 않은 내부 확인본/)).toBeInTheDocument();
    expect(screen.queryByText(/PoC용|시뮬레이션/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/실제 발송 없음/).length).toBeGreaterThan(0);
    expect(api.createCustomerCommunication).toHaveBeenCalledWith("case-1");
  });
});
