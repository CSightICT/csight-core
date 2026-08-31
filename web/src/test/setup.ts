import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import { sessionVault } from "../auth/sessionVault";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  sessionVault.clear();
});
