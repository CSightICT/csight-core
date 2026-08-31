import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as AuthProvider from "../auth/AuthProvider";
import { LoginPage } from "./LoginPage";

afterEach(() => vi.restoreAllMocks());

describe("LoginPage authentication modes", () => {
  it("shows only organization login when legacy password auth is disabled", () => {
    vi.spyOn(AuthProvider, "useAuth").mockReturnValue({
      user: null,
      busy: false,
      sessionExpired: false,
      sessionExpiresWithinFiveMinutes: false,
      oidcAvailable: true,
      legacyPasswordAvailable: false,
      login: vi.fn(async () => undefined),
      startOidcLogin: vi.fn(),
      logout: vi.fn(async () => undefined),
      hasRole: () => false,
    });

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    expect(screen.getByRole("button", { name: /조직 계정 로그인/ })).toBeInTheDocument();
    expect(screen.queryByText("기존 파일럿 로그인")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("비밀번호")).not.toBeInTheDocument();
  });
});
