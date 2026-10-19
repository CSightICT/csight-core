import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, expect, it, vi } from "vitest";
import { server } from "../test/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());
afterEach(() => { server.resetHandlers(); vi.unstubAllEnvs(); vi.resetModules(); });

it.each([true, false])("sends SHADOW only in an explicitly enabled feedback build (%s)", async (enabled) => {
  vi.stubEnv("VITE_INTERNAL_MODEL_FEEDBACK", String(enabled));
  vi.resetModules();
  let body: Record<string, unknown> = {};
  server.use(http.post("/api/v1/cases/feedback-case/analysis-runs", async ({ request }) => {
    body = await request.json() as Record<string, unknown>;
    return HttpResponse.json({ error: { code: "TEST_STOP", message: "Captured before execution" } }, { status: 422 });
  }));
  const { api } = await import("./client");
  await expect(api.startAnalysis("feedback-case", "product_defect_text_extraction", "2.0.0", "feedback-key")).rejects.toMatchObject({ code: "TEST_STOP" });
  expect(body.execution_mode).toBe(enabled ? "SHADOW" : undefined);
});
