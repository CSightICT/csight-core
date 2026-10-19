import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import * as AuthProvider from "../auth/AuthProvider";
import { server } from "../test/server";
import { OperationsPage } from "./OperationsPage";

function renderPage() {
  vi.spyOn(AuthProvider, "useAuth").mockReturnValue({
    user: { user_id: "admin-1", tenant_id: "tenant-1", email: "admin@example.test", display_name: "관리자", roles: ["ADMIN"] },
    busy: false,
    sessionExpired: false,
    sessionExpiresWithinFiveMinutes: false,
    oidcAvailable: true,
    legacyPasswordAvailable: false,
    login: vi.fn(async () => undefined),
    startOidcLogin: vi.fn(),
    logout: vi.fn(async () => undefined),
    hasRole: (role: string) => role === "ADMIN",
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><OperationsPage /></MemoryRouter></QueryClientProvider>);
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
});
afterAll(() => server.close());

describe("OperationsPage onboarding readiness", () => {
  it("shows actionable failed gates without exposing tenant identifiers", async () => {
    server.use(
      http.get("/api/v1/operations/onboarding-readiness", () => HttpResponse.json({
        pilot_ready: false,
        gates: [
          { code: "ACTIVE_OPERATOR_STAFFING", status: "PASS", description: "staffing ready" },
          { code: "SIGNED_INTAKE_SOURCE", status: "FAIL", description: "intake missing" },
          { code: "RETENTION_AUTOMATION", status: "PASS", description: "retention ready" },
          { code: "OIDC_TENANT_MAPPING", status: "PASS", description: "oidc ready" },
          { code: "ACTIVE_POLICY_RUNTIME", status: "PASS", description: "policy ready" },
          { code: "PRIMARY_MODEL_ROUTES", status: "FAIL", description: "routes missing" },
        ],
      })),
      http.get("/api/v1/operations/overview", () => HttpResponse.json({
        generated_at: "2026-08-31T00:00:00Z",
        stalled_after_seconds: 300,
        total_backlog_count: 0,
        total_stalled_count: 0,
        queues: [],
        processing: [],
        active_versions: [],
      })),
      http.get("/api/v1/operations/failures", () => HttpResponse.json({
        generated_at: "2026-08-31T00:00:00Z",
        lookback_seconds: 86400,
        total_failed_count: 0,
        total_partial_success_count: 0,
        total_retry_count: 0,
        total_stalled_count: 0,
        components: [],
      })),
    );

    renderPage();

    expect(await screen.findByText("아직 파일럿을 시작할 수 없습니다")).not.toBeVisible();
    fireEvent.click(screen.getByText("실운영 전환 설정 보기"));
    expect(screen.getByText("아직 파일럿을 시작할 수 없습니다")).toBeVisible();
    expect(screen.getByText("안전한 문의 접수")).toBeVisible();
    expect(screen.getByText("승인된 모델 경로")).toBeVisible();
    expect(screen.getByText("세 모델 작업의 승인 경로와 실행 보호를 모두 자격 검증해 주세요.")).toBeVisible();
    expect(document.body).not.toHaveTextContent("tenant-1");
  });
});
