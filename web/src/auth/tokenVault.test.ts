import { describe, expect, it, vi } from "vitest";

import { tokenVault } from "./tokenVault";

describe("tokenVault", () => {
  it("keeps the bearer token in memory and expires it", () => {
    vi.spyOn(Date, "now").mockReturnValue(1_000);
    tokenVault.set("secret-token", 30);
    expect(tokenVault.get()).toBe("secret-token");
    expect(sessionStorage.length).toBe(0);
    vi.spyOn(Date, "now").mockReturnValue(25_000);
    expect(tokenVault.get()).toBeNull();
    vi.restoreAllMocks();
  });
});
