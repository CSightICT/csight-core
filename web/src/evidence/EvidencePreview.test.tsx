import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { tokenVault } from "../auth/tokenVault";
import type { Evidence } from "../api/contracts";
import { server } from "../test/server";
import { EvidencePreview, type EvidencePreviewStatus } from "./EvidencePreview";

const evidence: Evidence = {
  evidence_id: "evidence-1",
  tenant_id: "tenant-1",
  case_id: "case-1",
  evidence_type: "IMAGE",
  upload_status: "AVAILABLE",
  original_filename: "rank-054.jpg",
  content_type: "image/jpeg",
  size_bytes: 905_141,
  sha256: "a".repeat(64),
  width: 2048,
  height: 2048,
  created_by: "user-1",
  created_at: "2026-08-28T00:00:00Z",
  updated_at: "2026-08-28T00:00:00Z",
};

const createObjectUrl = vi.fn(() => "blob:https://doongdoong.org/evidence-preview-1");
const revokeObjectUrl = vi.fn();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectUrl });
});
afterEach(() => {
  server.resetHandlers();
  tokenVault.clear();
  createObjectUrl.mockClear();
  revokeObjectUrl.mockClear();
});
afterAll(() => server.close());

function renderPreview(onStatusChange?: (evidenceId: string, status: EvidencePreviewStatus) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><EvidencePreview caseId="case-1" evidence={evidence} {...(onStatusChange ? { onStatusChange } : {})} /></QueryClientProvider>);
}

describe("EvidencePreview", () => {
  it("loads authenticated same-origin bytes, displays a Blob thumbnail, and revokes it on cleanup", async () => {
    let authorization: string | null = null;
    server.use(http.get("/api/v1/cases/case-1/evidence/evidence-1/content", ({ request }) => {
      authorization = request.headers.get("Authorization");
      return new HttpResponse(new Uint8Array([0xff, 0xd8, 0xff, 0xd9]), {
        headers: { "Content-Type": "image/jpeg", "Cache-Control": "no-store" },
      });
    }));
    tokenVault.set("preview-token", 600);

    const view = renderPreview();
    const image = await screen.findByRole("img", { name: "rank-054.jpg 증거 미리보기" });
    expect(image).toHaveAttribute("src", "blob:https://doongdoong.org/evidence-preview-1");
    expect(screen.getByRole("link", { name: "rank-054.jpg 원본 새 탭에서 열기" })).toHaveAttribute("target", "_blank");
    expect(authorization).toBe("Bearer preview-token");
    expect(document.body).not.toHaveTextContent("127.0.0.1:9000");

    view.unmount();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:https://doongdoong.org/evidence-preview-1");
  });

  it("reports loading and only becomes ready after the browser decodes the image", async () => {
    server.use(http.get("/api/v1/cases/case-1/evidence/evidence-1/content", () => new HttpResponse(
      new Uint8Array([0xff, 0xd8, 0xff, 0xd9]),
      { headers: { "Content-Type": "image/jpeg" } },
    )));
    tokenVault.set("preview-token", 600);
    const onStatusChange = vi.fn();
    renderPreview(onStatusChange);

    const image = await screen.findByRole("img", { name: "rank-054.jpg 증거 미리보기" });
    expect(onStatusChange).toHaveBeenCalledWith("evidence-1", "LOADING");
    expect(onStatusChange).not.toHaveBeenCalledWith("evidence-1", "READY");

    fireEvent.load(image);
    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith("evidence-1", "READY"));
  });

  it("falls back to metadata without leaving a broken image when decoding fails", async () => {
    server.use(http.get("/api/v1/cases/case-1/evidence/evidence-1/content", () => new HttpResponse(
      new Uint8Array([0xff, 0xd8, 0xff, 0xd9]),
      { headers: { "Content-Type": "image/jpeg" } },
    )));
    tokenVault.set("preview-token", 600);
    const view = renderPreview();
    const image = await screen.findByRole("img", { name: "rank-054.jpg 증거 미리보기" });

    fireEvent.error(image);
    expect(screen.getByText("미리보기를 표시할 수 없어 파일 정보만 제공합니다.")).toBeVisible();
    expect(screen.queryByRole("img", { name: "rank-054.jpg 증거 미리보기" })).not.toBeInTheDocument();
    expect(screen.getByText("rank-054.jpg")).toBeVisible();
    expect(screen.getByRole("button", { name: /다시 시도/ })).toBeVisible();
    view.unmount();
  });

  it("reports a failed fetch and returns to ready only after retry and decode", async () => {
    let attempt = 0;
    server.use(http.get("/api/v1/cases/case-1/evidence/evidence-1/content", () => {
      attempt += 1;
      return attempt === 1
        ? new HttpResponse("<html>not evidence</html>", { headers: { "Content-Type": "text/html" } })
        : new HttpResponse(new Uint8Array([0xff, 0xd8, 0xff, 0xd9]), { headers: { "Content-Type": "image/jpeg" } });
    }));
    tokenVault.set("preview-token", 600);
    const onStatusChange = vi.fn();
    renderPreview(onStatusChange);

    const retry = await screen.findByRole("button", { name: /다시 시도/ });
    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith("evidence-1", "FAILED"));
    fireEvent.click(retry);
    const image = await screen.findByRole("img", { name: "rank-054.jpg 증거 미리보기" });
    expect(onStatusChange).not.toHaveBeenLastCalledWith("evidence-1", "READY");
    fireEvent.load(image);
    await waitFor(() => expect(onStatusChange).toHaveBeenLastCalledWith("evidence-1", "READY"));
  });

  it("rejects a non-image response and exposes no original link", async () => {
    server.use(http.get("/api/v1/cases/case-1/evidence/evidence-1/content", () => new HttpResponse(
      "<html>not evidence</html>",
      { headers: { "Content-Type": "text/html" } },
    )));
    tokenVault.set("preview-token", 600);
    renderPreview();

    expect(await screen.findByText("미리보기를 표시할 수 없어 파일 정보만 제공합니다.")).toBeVisible();
    expect(screen.queryByRole("link", { name: /원본 새 탭/ })).not.toBeInTheDocument();
  });
});
