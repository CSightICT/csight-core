import { describe, expect, it, vi } from "vitest";

import { sessionVault } from "./sessionVault";

describe("sessionVault", () => {
  it("keeps CSRF only in memory until the effective session expiry", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-29T00:00:00Z"));
    sessionVault.set("csrf-token-value", {
      idle_expires_at: "2026-08-29T00:30:00Z",
      absolute_expires_at: "2026-08-29T08:00:00Z",
      effective_expires_at: "2026-08-29T00:30:00Z",
      expiry_warning_at: "2026-08-29T00:25:00Z",
      expires_in_seconds: 1800,
      expires_within_five_minutes: false,
    });

    expect(sessionVault.csrf()).toBe("csrf-token-value");
    vi.setSystemTime(new Date("2026-08-29T00:30:00Z"));
    expect(sessionVault.csrf()).toBeNull();
    expect(sessionStorage.length).toBe(0);
    vi.useRealTimers();
  });
});
