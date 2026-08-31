import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { tokenVault } from "../auth/tokenVault";
import { sessionVault } from "../auth/sessionVault";
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

describe("operator queue contract", () => {
  it("normalizes omitted optional projection fields without dropping the row", async () => {
    server.use(http.get("/api/v1/operator/cases", () => HttpResponse.json({
      items: [{
        case_id: "case-1", case_status: "UNKNOWN_FUTURE_STATE", order_ref: "ORD-1", product_ref: "SKU-1",
        requested_action: "UNKNOWN_ACTION", created_at: "2026-08-29T00:00:00Z", updated_at: "2026-08-29T01:00:00Z",
        assignment_version: 0,
      }],
      counts: { all: 1, my: 0, unassigned: 1, urgent: 0, waiting_evidence: 0, complete: 0 },
    })));
    tokenVault.set("test-token", 600);

    const page = await api.listOperatorCases({ view: "all", sort: "newest" });

    expect(page.items).toHaveLength(1);
    expect(page.items[0]).toMatchObject({
      case_id: "case-1",
      case_status: "UNKNOWN_FUTURE_STATE",
      assignee_id: null,
      review_status: null,
      report_id: null,
    });
    expect(page.next_cursor).toBeNull();
  });

  it("sends server-side queue search with the projection request", async () => {
    let observedQuery: string | null = null;
    server.use(http.get("/api/v1/operator/cases", ({ request }) => {
      observedQuery = new URL(request.url).searchParams.get("q");
      return HttpResponse.json({
        items: [],
        counts: { all: 0, my: 0, unassigned: 0, urgent: 0, waiting_evidence: 0, complete: 0 },
        next_cursor: null,
      });
    }));
    tokenVault.set("test-token", 600);

    await api.listOperatorCases({ view: "all", sort: "newest", q: "ORD-ALPHA" });

    expect(observedQuery).toBe("ORD-ALPHA");
  });
});

describe("OIDC browser session contract", () => {
  it("uses the HttpOnly session cookie path and sends the in-memory CSRF token on mutations", async () => {
    let observedAuthorization: string | null = null;
    let observedCsrf: string | null = null;
    server.use(http.post("/api/v1/cases", ({ request }) => {
      observedAuthorization = request.headers.get("Authorization");
      observedCsrf = request.headers.get("X-CSRF-Token");
      return HttpResponse.json({ case_id: "case-oidc", status: "RECEIVED", created_at: "2026-08-29T00:00:00Z" });
    }));
    sessionVault.set("c".repeat(43), {
      idle_expires_at: "2099-01-01T00:00:00Z",
      absolute_expires_at: "2099-01-01T00:00:00Z",
      effective_expires_at: "2099-01-01T00:00:00Z",
      expiry_warning_at: "2098-12-31T23:55:00Z",
      expires_in_seconds: 1800,
      expires_within_five_minutes: false,
    });

    await api.createCase({
      order_ref: "ORD-1", product_ref: "SKU-1", customer_message: "문의 내용",
      requested_action: "REFUND", attributes: {},
    }, "case-key");

    expect(observedAuthorization).toBeNull();
    expect(observedCsrf).toBe("c".repeat(43));
  });
});

describe("operations read contract", () => {
  it("decodes bounded aggregate operations responses without identifier labels", async () => {
    server.use(http.get("/api/v1/operations/overview", () => HttpResponse.json({
      generated_at: "2026-08-29T00:00:00Z", stalled_after_seconds: 300,
      total_backlog_count: 2, total_stalled_count: 1,
      queues: [{
        queue: "analysis_dispatch", backlog_count: 2, pending_count: 1, processing_count: 1,
        published_unconsumed_count: 0, failed_count: 0, retry_count: 1, stalled_count: 1,
        oldest_backlog_age_seconds: 420, last_healthy_at: "2026-08-28T23:59:00Z",
      }], processing: [], active_versions: [],
    })));
    tokenVault.set("test-token", 600);

    const overview = await api.getOperationsOverview();

    expect(overview.total_backlog_count).toBe(2);
    expect(overview.queues[0]).toMatchObject({ queue: "analysis_dispatch", stalled_count: 1 });
    expect(JSON.stringify(overview)).not.toContain("tenant_id");
    expect(JSON.stringify(overview)).not.toContain("case_id");
  });

  it("decodes the PII-free onboarding gate contract", async () => {
    server.use(http.get("/api/v1/operations/onboarding-readiness", () => HttpResponse.json({
      pilot_ready: false,
      gates: [
        "ACTIVE_OPERATOR_STAFFING",
        "SIGNED_INTAKE_SOURCE",
        "RETENTION_AUTOMATION",
        "OIDC_TENANT_MAPPING",
        "ACTIVE_POLICY_RUNTIME",
        "PRIMARY_MODEL_ROUTES",
      ].map((code) => ({ code, status: code === "ACTIVE_OPERATOR_STAFFING" ? "PASS" : "FAIL", description: `${code} status` })),
    })));
    tokenVault.set("test-token", 600);

    const readiness = await api.getOnboardingReadiness();

    expect(readiness.pilot_ready).toBe(false);
    expect(readiness.gates).toHaveLength(6);
    expect(JSON.stringify(readiness)).not.toContain("tenant_id");
    expect(JSON.stringify(readiness)).not.toContain("user_id");
  });
});
