import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { DemoResetPanel } from "./DemoResetPanel";

afterEach(() => vi.restoreAllMocks());
it("requires confirmation, sends the fresh fingerprint, and refreshes after reset", async () => {
  const preview = { enabled: true, count: 2, fingerprint: "a".repeat(64), reset_id: null };
  vi.spyOn(api, "previewDemoReset").mockResolvedValue(preview);
  const reset = vi.spyOn(api, "resetDemoReviews").mockResolvedValue({ ...preview, reset_id: "reset-1" });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(<QueryClientProvider client={client}><DemoResetPanel /></QueryClientProvider>);
  await waitFor(() => expect(screen.getByRole("button", { name: "DB 적재 원복" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "DB 적재 원복" }));
  expect(await screen.findByRole("alertdialog")).toHaveTextContent("2건");
  expect(reset).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "취소" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "DB 적재 원복" }));
  await screen.findByRole("alertdialog");
  fireEvent.click(screen.getByRole("button", { name: "검토 대기로 원복" }));
  expect(await screen.findByRole("status")).toHaveTextContent("2건을 검토 대기");
  expect(reset).toHaveBeenCalledWith(preview.fingerprint);
  expect(invalidate).toHaveBeenCalled();
});
