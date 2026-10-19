import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as AuthProvider from "../auth/AuthProvider";
import { AppShell } from "./AppShell";


afterEach(() => {
  vi.restoreAllMocks();
});

describe("AppShell reviewer navigation", () => {
  it("separates assigned waiting inquiries from the reviewer's completed inquiries", () => {
    vi.spyOn(AuthProvider, "useAuth").mockReturnValue({
      user: {
        user_id: "reviewer-1",
        tenant_id: "tenant-1",
        email: "reviewer@test.local",
        display_name: "담당자",
        roles: ["REVIEWER"],
      },
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

    render(<MemoryRouter initialEntries={["/cases"]}><Routes>
      <Route element={<AppShell />}>
        <Route path="/cases" element={<p>문의 대기 화면</p>} />
      </Route>
    </Routes></MemoryRouter>);

    expect(screen.getByRole("link", { name: "문의 대기" })).toHaveAttribute("href", "/cases");
    expect(screen.getByRole("link", { name: "내 문의 처리 현황" })).toHaveAttribute("href", "/reviews");
    expect(screen.queryByRole("link", { name: "상담 케이스" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "검토함" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "운영 상태" })).not.toBeInTheDocument();
    expect(screen.queryByText(/실모델 피드백 모드/)).not.toBeInTheDocument();
  });
});
