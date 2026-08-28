import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { tokenVault } from "../auth/tokenVault";
import { server } from "../test/server";
import { ApiError, api } from "./client";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  tokenVault.clear();
});
afterAll(() => server.close());

describe("API error contract", () => {
  it("shows the server's structured CSight error instead of a generic HTTP status", async () => {
    server.use(http.post("/api/v1/cases/case-1/policy-evaluation-runs", () => HttpResponse.json({
      error: {
        code: "VALIDATION_ERROR",
        message: "No active policy rule set is valid for as_of_date.",
        details: {},
        correlation_id: "correlation-1",
      },
    }, { status: 422 })));
    tokenVault.set("test-token", 600);

    const request = api.startPolicy("case-1", "analysis-1", "2026-08-27", "key-1");
    await expect(request).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      code: "VALIDATION_ERROR",
      message: "No active policy rule set is valid for as_of_date.",
    } satisfies Partial<ApiError>);
  });
});
