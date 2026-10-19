import { render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import * as AuthProvider from "./auth/AuthProvider";

afterEach(() => vi.restoreAllMocks());

function renderAt(path: string) {
  vi.spyOn(AuthProvider, "useAuth").mockReturnValue({
    user: null,
    busy: false,
    sessionExpired: false,
    sessionExpiresWithinFiveMinutes: false,
    oidcAvailable: false,
    legacyPasswordAvailable: true,
    login: vi.fn(async () => undefined),
    startOidcLogin: vi.fn(),
    logout: vi.fn(async () => undefined),
    hasRole: () => false,
  });

  function RoutePath() {
    return <output data-testid="route-path">{useLocation().pathname}</output>;
  }

  render(<MemoryRouter initialEntries={[path]}><App /><RoutePath /></MemoryRouter>);
}

describe("public login route", () => {
  it("shows the existing login form at /login2", async () => {
    renderAt("/login2");

    expect(await screen.findByRole("heading", { name: "기존 파일럿 로그인" })).toBeInTheDocument();
    expect(screen.getByLabelText("비밀번호")).toBeInTheDocument();
    expect(screen.getByTestId("route-path")).toHaveTextContent("/login2");
  });

  it("redirects signed-out users to /login2", async () => {
    renderAt("/cases");

    expect(await screen.findByRole("heading", { name: "기존 파일럿 로그인" })).toBeInTheDocument();
    expect(screen.getByTestId("route-path")).toHaveTextContent("/login2");
  });
});
