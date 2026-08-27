import type { Page, Route } from "@playwright/test";

export type DemoScenario = "validated" | "needs-input" | "evidence" | "safety" | "vision-timeout";

const now = "2026-08-27T06:00:00Z";

function taskFor(scenario: DemoScenario) {
  const status = scenario === "evidence" ? "WAITING_FOR_EVIDENCE" : scenario === "validated" || scenario === "needs-input" ? "RESOLVED" : scenario === "safety" ? "CLAIMED" : "PENDING";
  return {
    id: `task-${scenario}`, case_id: `case-${scenario}`, policy_evaluation_run_id: `policy-${scenario}`,
    task_type: scenario === "safety" ? "SAFETY_REVIEW" : scenario === "evidence" ? "EVIDENCE_REVIEW" : "STANDARD_REVIEW",
    priority: scenario === "safety" ? "CRITICAL" : "NORMAL", status,
    current_assignee_id: status === "CLAIMED" ? "user-1" : null, version: 2,
    mapping_rule_name: "policy_evaluation_to_human_review", mapping_rule_version: "1.0.0",
    created_at: now, updated_at: now, resolved_at: status === "RESOLVED" ? now : null,
  };
}

function caseFor(scenario: DemoScenario) {
  const action = scenario === "validated" ? "REPAIR" : scenario === "needs-input" ? "REFUND" : "UNSPECIFIED";
  const external = scenario === "validated" ? { quantity: 1 } : {};
  return {
    case_id: `case-${scenario}`, tenant_id: "tenant-1", domain_type: "product_defect_cs", status: "OPEN",
    order_ref: `ORD-${scenario.toUpperCase()}`, product_ref: `SKU-${scenario.toUpperCase()}`,
    requested_action: action, created_at: now, updated_at: now,
    customer_message: scenario === "evidence" ? "결함이 있지만 사진을 아직 첨부하지 못했습니다." : "제품 결함을 확인하고 정책에 맞게 처리해 주세요.",
    attributes: Object.keys(external).length ? { external_action_input: external } : {}, created_by: "user-1",
    evidence: scenario === "evidence" ? [] : [{
      evidence_id: `evidence-${scenario}`, tenant_id: "tenant-1", case_id: `case-${scenario}`,
      evidence_type: "IMAGE", upload_status: "AVAILABLE", original_filename: "defect.jpg", content_type: "image/jpeg",
      size_bytes: 204800, sha256: "a".repeat(64), width: 1200, height: 900, created_by: "user-1", created_at: now, updated_at: now,
    }],
    status_history: [], latest_analysis_run: null,
  };
}

function reviewDetail(scenario: DemoScenario) {
  const task = taskFor(scenario);
  return {
    task,
    packet: {
      review_packet_id: `packet-${scenario}`, llm_extraction_result_v2_id: `extraction-${scenario}`,
      policy_recommendation: scenario === "safety" ? "MANAGER_REVIEW" : "APPROVE_REPAIR",
      input_qualification: "QUALIFIED_FOR_HUMAN_REVIEW",
    },
    actions: [{ id: "action-created", action_type: "CREATED", created_at: now }],
    decision: task.status === "RESOLVED" ? { decision: scenario === "validated" ? "APPROVE_REPAIR" : "APPROVE_REFUND", rationale: "정책 근거와 고객 증거를 확인했습니다." } : null,
    rule_results: [{ id: `rule-result-${scenario}`, rule_id: "product_defect.coverage", status: "PASS" }],
    citation_items: [{ citation_id: `citation-${scenario}`, clause_id: "POLICY-4.2", document_version: "2026-08" }],
    grounded_explanation: { summary: "정책 조항이 고객의 결함 상황과 요청을 뒷받침합니다." },
  };
}

function analysisDetail(scenario: DemoScenario) {
  const status = scenario === "vision-timeout" ? "PARTIAL_SUCCESS" : "SUCCEEDED";
  return {
    run: {
      analysis_run_id: `vision-${scenario}`, tenant_id: "tenant-1", case_id: `case-${scenario}`,
      pipeline: "product_defect_multimodal_analysis", pipeline_version: "1.0.0", trigger: "MANUAL",
      status, requested_by: "user-1", requested_at: now, started_at: now, completed_at: now,
      failure: null, created_at: now, updated_at: now,
    },
    stages: [{
      stage_run_id: "stage-vision", stage_type: "VISION_ANALYSIS", status: "FAILED", model_name: "mock-vision",
      model_version: "0.1.0", prompt_version: "1.0.0", attempt_count: 3,
    }],
    extraction_result: null, extraction_result_v2: null, vision_results: [], failed_stages: ["VISION_ANALYSIS"],
  };
}

async function json(route: Route, value: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(value) });
}

export async function installApi(page: Page, scenario: DemoScenario) {
  let role = "REVIEWER";
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path === "/api/v1/auth/token") {
      const body = request.postDataJSON() as { email?: string };
      role = body.email?.startsWith("admin") ? "ADMIN" : "REVIEWER";
      return json(route, { access_token: `token-${role}`, token_type: "bearer", expires_in: 3600 });
    }
    if (path === "/api/v1/auth/me") return json(route, { user_id: "user-1", tenant_id: "tenant-1", email: `${role.toLowerCase()}@demo.test`, display_name: role === "ADMIN" ? "관리자" : "검토자", roles: [role] });
    if (path === "/api/v1/cases" && request.method() === "GET") {
      const item = caseFor(scenario);
      const { customer_message: _message, attributes: _attributes, created_by: _createdBy, evidence: _evidence, status_history: _history, latest_analysis_run: _latest, ...summary } = item;
      return json(route, { items: [summary], page: 1, page_size: 100, total: 1 });
    }
    if (path === `/api/v1/cases/case-${scenario}/human-review-tasks`) return json(route, { items: [taskFor(scenario)] });
    if (path === `/api/v1/cases/case-${scenario}/resolution/events`) return json(route, { items: scenario === "validated" || scenario === "needs-input" ? [{ event_id: "resolution-event-1" }] : [] });
    if (path === `/api/v1/cases/case-${scenario}/external-action-intents`) {
      if (scenario === "validated") return json(route, { items: [{
        id: "intent-1", case_id: `case-${scenario}`, resolution_id: "resolution-1", human_decision_id: "decision-1",
        action_type: "REPAIR", mode: "DRY_RUN", order_ref: "ORD-VALIDATED", product_ref: "SKU-VALIDATED",
        amount: null, currency: null, quantity: 1, shipping_address_ref: null,
        mapping_name: "human_decision_to_external_action", mapping_version: "1.0.0", intent_schema_version: "1.0.0",
        content_hash: "intent-hash", created_at: now,
      }] });
      return json(route, { items: [] });
    }
    if (path === "/api/v1/external-action-intents/intent-1") return json(route, {
      intent: {
        id: "intent-1", case_id: "case-validated", resolution_id: "resolution-1", human_decision_id: "decision-1",
        action_type: "REPAIR", mode: "DRY_RUN", order_ref: "ORD-VALIDATED", product_ref: "SKU-VALIDATED",
        amount: null, currency: null, quantity: 1, shipping_address_ref: null,
        mapping_name: "human_decision_to_external_action", mapping_version: "1.0.0", intent_schema_version: "1.0.0",
        content_hash: "intent-hash", created_at: now,
      },
      attempts: [{
        id: "attempt-1", case_id: "case-validated", resolution_id: "resolution-1", external_action_intent_id: "intent-1",
        attempt_number: 1, status: "SUCCEEDED", mode: "DRY_RUN", started_at: now, completed_at: now,
        failure_code: null, failure_message: null,
      }],
      results: [{
        id: "result-1", case_id: "case-validated", resolution_id: "resolution-1", external_action_intent_id: "intent-1",
        simulation_attempt_id: "attempt-1", outcome: "VALIDATED", mode: "DRY_RUN", side_effects_performed: false,
        failure_code: null, failure_message: null, simulated_request: { action_type: "REPAIR" }, simulated_response: { validated: true },
        result_schema_version: "1.0.0", content_hash: "result-hash", created_at: now,
      }],
    });
    if (path === `/api/v1/cases/case-${scenario}/resolution`) {
      const base = {
        id: `resolution-${scenario}`, case_id: `case-${scenario}`, source_review_task_id: `task-${scenario}`,
        source_human_decision_id: `decision-${scenario}`, version: 2, mapping_name: "human_decision_to_external_action",
        mapping_version: "1.0.0", resolution_schema_version: "1.0.0", invalid_fields: [], failure_code: null,
        failure_message: null, correlation_id: `correlation-${scenario}`, created_at: now, updated_at: now,
      };
      if (scenario === "validated") return json(route, { ...base, status: "ACTION_DRY_RUN_VALIDATED", missing_fields: [] });
      if (scenario === "needs-input") return json(route, { ...base, status: "ACTION_NEEDS_INPUT", missing_fields: ["amount", "currency"] });
      return json(route, { detail: { code: "CASE_RESOLUTION_NOT_FOUND", message: "No resolution" } }, 404);
    }
    if (path === `/api/v1/cases/case-${scenario}/analysis-runs/vision-${scenario}`) return json(route, analysisDetail(scenario));
    if (path === `/api/v1/cases/case-${scenario}`) return json(route, caseFor(scenario));
    if (path === "/api/v1/human-review-tasks") return json(route, { items: [taskFor(scenario)] });
    if (path === `/api/v1/human-review-tasks/task-${scenario}`) return json(route, reviewDetail(scenario));
    if (path.startsWith(`/api/v1/human-review-tasks/task-${scenario}/`) && request.method() === "POST") {
      return json(route, { task: { ...taskFor(scenario), status: "RESOLVED", version: 3, resolved_at: now }, decision: { decision: "APPROVE_REPAIR" } });
    }
    return json(route, { detail: { code: "FIXTURE_ROUTE_MISSING", message: path } }, 404);
  });
}

export async function login(page: Page, email = "reviewer@demo.test") {
  await page.goto("/login");
  await page.getByLabel("조직 슬러그").fill("demo");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill("demo-password");
  await page.getByRole("button", { name: "로그인" }).click();
  await page.waitForURL("**/cases");
}

export async function navigateInSession(page: Page, path: string) {
  await page.evaluate((nextPath) => {
    window.history.pushState({}, "", nextPath);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}
