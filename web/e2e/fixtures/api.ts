import type { Page, Route } from "@playwright/test";

export type DemoScenario = "validated" | "needs-input" | "evidence" | "safety" | "vision-timeout";

const now = "2026-08-27T06:00:00Z";
const previewPng = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGPUashlYGBgYgADAAz7ARtxcqT5AAAAAElFTkSuQmCC", "base64");

function taskFor(scenario: DemoScenario) {
  const status = scenario === "evidence" ? "WAITING_FOR_EVIDENCE" : scenario === "validated" || scenario === "needs-input" ? "RESOLVED" : scenario === "safety" ? "CLAIMED" : "PENDING";
  const ownedByReviewer = status === "CLAIMED" || status === "WAITING_FOR_EVIDENCE";
  return {
    id: `task-${scenario}`, case_id: `case-${scenario}`, policy_evaluation_run_id: `policy-${scenario}`,
    task_type: scenario === "safety" ? "SAFETY_REVIEW" : scenario === "evidence" ? "EVIDENCE_REVIEW" : "STANDARD_REVIEW",
    priority: scenario === "safety" ? "CRITICAL" : "NORMAL", status,
    current_assignee_id: ownedByReviewer ? "user-1" : null, version: 2,
    mapping_rule_name: "policy_evaluation_to_human_review", mapping_rule_version: "1.0.0",
    created_at: now, updated_at: now, resolved_at: status === "RESOLVED" ? now : null,
  };
}

function caseFor(scenario: DemoScenario) {
  const action = scenario === "validated" ? "REPAIR" : scenario === "needs-input" ? "REFUND" : "UNSPECIFIED";
  const external = scenario === "validated" ? { quantity: 1 } : {};
  const messages: Record<DemoScenario, string> = {
    validated: "지난주 CSight Commerce에서 주문한 무선 청소기를 오늘 처음 사용했습니다. 전원은 켜지지만 브러시가 회전하지 않고 본체 아래쪽에서 반복적으로 긁히는 소리가 납니다. 설명서에 나온 초기 점검과 재장착도 해봤지만 같은 증상이 계속됩니다. 수리가 가능한 제품이면 우선 수리를 받고 싶고, 수리가 어렵다면 동일 상품 교환이 가능한지 확인해 주세요. 주문 내역과 고장 부위 사진을 함께 첨부했습니다.",
    "needs-input": "어제 배송받은 보온 텀블러의 뚜껑 결합부가 깨져 있어 물을 넣으면 바로 새어 나옵니다. 포장 상자에는 눌림이 없었고 상품을 세척하거나 실제로 사용하지도 않았습니다. 같은 상품으로 다시 받기보다 이번 주문은 환불을 요청하고 싶습니다. 다만 쿠폰과 포인트를 함께 사용해서 최종 환불 금액과 환불 수단이 어떻게 되는지는 잘 모르겠습니다. 사진과 주문 번호를 기준으로 환불 가능 여부를 먼저 검토해 주세요.",
    evidence: "오늘 받은 수납함을 열어 보니 바닥 모서리에 길게 금이 가 있고 살짝 누르면 틈이 더 벌어집니다. 배송 상자 한쪽도 찌그러져 있어서 운송 중 손상된 것으로 보입니다. 내용물을 꺼내는 과정에서 손상 부위를 발견해 상품은 아직 사용하지 않았습니다. 가능하면 동일 상품으로 교환하고 싶지만 지금은 이동 중이라 사진을 첨부하지 못했습니다. 필요한 사진 종류를 알려주시면 귀가 후 추가로 제출하겠습니다.",
    safety: "유아용 전기포트를 처음 가열하던 중 손잡이 연결부에서 타는 냄새와 옅은 연기가 발생해 즉시 전원을 뽑았습니다. 아이가 사용하는 제품이라 다시 작동해 보는 것은 위험할 것 같아 그대로 보관 중입니다. 본체 외관에는 큰 파손이 없지만 손잡이 주변이 평소보다 뜨거웠습니다. 단순 반품으로 처리해도 되는지, 별도의 안전 사고 접수와 회수가 필요한지 안내해 주세요. 주문 번호와 제품 사진은 첨부했으며 추가 사용은 하지 않겠습니다.",
    "vision-timeout": "여행 전에 받은 캐리어를 확인하던 중 오른쪽 앞바퀴 축 주변에 미세한 균열이 보였습니다. 빈 상태에서도 바퀴가 한쪽으로 기울고 바닥에서 끌리는 소리가 납니다. 포장재를 제거한 직후 발견해 외부에서 사용한 적은 없습니다. 출국 일정이 가까워 수리보다 빠른 교환이 가능한지 확인하고 싶습니다. 전체 모습과 바퀴 근접 사진을 첨부했으니 이미지 확인이 지연되더라도 사람 검토로 이어서 처리해 주세요.",
  };
  const imageObservations: Record<DemoScenario, string> = {
    validated: "본체 아래 브러시 하우징과 장착부 외관이 촬영되어 있습니다.",
    "needs-input": "뚜껑 결합부의 균열과 가장자리 파손이 보입니다.",
    evidence: "첨부 이미지가 없어 확인된 시각 정보가 없습니다.",
    safety: "손잡이 연결부와 본체 외관이 촬영되어 있습니다.",
    "vision-timeout": "오른쪽 앞바퀴 축 주변과 바퀴 정렬 상태가 촬영되어 있습니다.",
  };
  return {
    case_id: `case-${scenario}`, tenant_id: "tenant-1", domain_type: "product_defect_cs", status: "OPEN",
    order_ref: `ORD-${scenario.toUpperCase()}`, product_ref: `SKU-${scenario.toUpperCase()}`,
    requested_action: action, created_at: now, updated_at: now,
    customer_message: messages[scenario],
    attributes: {
      ...(Object.keys(external).length ? { external_action_input: external } : {}),
      demo_image_observation: imageObservations[scenario],
      demo_claim_boundary: "CUSTOMER_STATEMENT_ONLY_FOR_NON_VISIBLE_FACTS",
      realistic_demo: {
        schema_version: "2.0", dataset_id: "realistic-internal-demo-v2",
        scenario_scope: "INTERNAL_CURATED_ECOMMERCE_INQUIRY_6_DEFECT_4_BELOW_THRESHOLD",
        narrative_revision: "VISUAL_ALIGNED_R1",
        source_grade: "KAPUTT_SELECTED_CORRECT_POSITIVE",
        selection_bias: "FIXTURE_SYNTHETIC_NARRATIVE",
        rights_status: "INTERNAL_RESTRICTED_PROVENANCE_UNVERIFIED",
        policy_input_linkage: "NOT_LINKED_TO_POLICY_INPUT",
      },
    }, created_by: "user-1",
    evidence: scenario === "evidence" ? [] : [{
      evidence_id: `evidence-${scenario}`, tenant_id: "tenant-1", case_id: `case-${scenario}`,
      evidence_type: "IMAGE", upload_status: "AVAILABLE", original_filename: "defect.jpg", content_type: "image/jpeg",
      size_bytes: 204800, sha256: "a".repeat(64), width: 1200, height: 900, created_by: "user-1", created_at: now, updated_at: now,
    }],
    status_history: [], latest_analysis_run: null,
  };
}

function reviewDetail(scenario: DemoScenario, task = taskFor(scenario)) {
  const eligibility: Record<DemoScenario, string> = {
    validated: "REPAIR_REVIEW",
    "needs-input": "REFUND_REVIEW",
    evidence: "EXCHANGE_REVIEW",
    safety: "RETURN_REVIEW",
    "vision-timeout": "EXCHANGE_REVIEW",
  };
  return {
    task,
    packet: {
      review_packet_id: `packet-${scenario}`, llm_extraction_result_v2_id: `extraction-${scenario}`,
      policy_summary_status: scenario === "evidence" ? "REQUIRES_ADDITIONAL_EVIDENCE" : "REQUIRES_HUMAN_REVIEW",
      qualification_snapshot: { llm: { scope: "MOCK_QUALIFIED" }, grounding: { scope: "LOCAL_POC" } },
      policy_effects: [
        { type: "MARK_REVIEW_ELIGIBILITY", value: eligibility[scenario] },
        { type: "REQUIRE_HUMAN_REVIEW", value: null },
        { type: "PROHIBIT_AUTOMATION", value: null },
      ],
    },
    actions: [{ id: "action-created", action_type: "CREATED", created_at: now }],
    decision: task.status === "RESOLVED" ? { decision: scenario === "validated" ? "APPROVE_REPAIR" : "APPROVE_REFUND", rationale: "정책 근거와 고객 증거를 확인했습니다." } : null,
    rule_results: [{
      id: `rule-result-${scenario}`, rule_id: "CSCC-DEFECT-REVIEW-04", rule_version: "1.0.0",
      status: "MATCHED", effects: ["REQUIRE_HUMAN_REVIEW"],
    }],
    citation_items: [{
      citation_id: `citation-${scenario}`, clause_id: "CSCC-OPS-4.2", document_version: "2026.08-demo",
      title: "CSight Commerce 상품 하자 반품·교환 운영정책", section_path: ["4. 상품 하자", "4.2 검토 및 처리"],
      text: "상품 하자 문의는 주문 정보와 제출된 증거를 확인한 뒤 담당자의 검토를 거쳐 반품·교환·수리 권고 후보로 분류한다.",
    }],
    grounded_explanation: { summary: "가상 사내 정책의 상품 하자 검토 조항이 현재 문의의 주문 정보와 제출 증거 범위를 뒷받침합니다." },
    inquiry_summary: `${caseFor(scenario).product_ref} 상품의 상태와 요청 조치를 정책 근거에 따라 검토해야 하는 문의입니다.`,
    policy_similarity: [
      ["NEAREST", 1, 0.91, "CSCC-OPS-4.2", "상품 하자 검토", "주문 정보와 제출 증거를 확인한 뒤 담당자가 처리 후보를 검토합니다."],
      ["NEAREST", 2, 0.82, "CSCC-OPS-4.3", "교환·수리 선택", "상품 상태와 고객 요청을 함께 확인해 교환 또는 수리 후보를 검토합니다."],
      ["NEAREST", 3, 0.74, "CSCC-OPS-2.1", "접수 정보 확인", "주문 번호와 상품 정보가 접수 내용과 일치하는지 확인합니다."],
      ["LEAST", 1, 0.08, "CSCC-OPS-9.1", "회원 등급 변경", "회원 등급과 혜택 변경에 관한 운영 기준입니다."],
      ["LEAST", 2, 0.12, "CSCC-OPS-8.2", "배송지 변경", "출고 전 배송지 수정 요청에 관한 운영 기준입니다."],
      ["LEAST", 3, 0.16, "CSCC-OPS-7.3", "쿠폰 재발급", "프로모션 쿠폰 재발급 조건에 관한 운영 기준입니다."],
    ].map(([group, rank, cosine_similarity, policy_clause_id, title, text]) => ({
      group, rank, cosine_similarity, reference_threshold: 0.65,
      threshold_version: "policy_similarity_reference/1.0.0",
      reason_codes: group === "LEAST"
        ? ["LOWEST_COSINE_SIMILARITY", "POLICY_CONTEXT_MISMATCH"]
        : [Number(cosine_similarity) >= 0.65 ? "ABOVE_REFERENCE_THRESHOLD" : "BELOW_REFERENCE_THRESHOLD"],
      policy_clause_id, title, text,
    })),
  };
}

function textRunFor(scenario: DemoScenario) {
  return {
    analysis_run_id: `text-${scenario}`, tenant_id: "tenant-1", case_id: `case-${scenario}`,
    pipeline: "product_defect_text_extraction", pipeline_version: "2.0.0", trigger: "MANUAL",
    status: "SUCCEEDED", requested_by: "user-1", requested_at: now, started_at: now,
    completed_at: now, failure: null, created_at: now, updated_at: now,
  };
}

function policyRunsFor(scenario: DemoScenario) {
  const summary = scenario === "evidence"
    ? "REQUIRES_ADDITIONAL_EVIDENCE"
    : "REQUIRES_HUMAN_REVIEW";
  const lifecycle = {
    case_id: `case-${scenario}`, status: "SUCCEEDED", correlation_id: `correlation-${scenario}`,
    created_at: now, started_at: now, completed_at: now, failure_code: null, failure_message: null,
  };
  return {
    retrieval: {
      ...lifecycle, id: `retrieval-${scenario}`, analysis_run_id: `text-${scenario}`,
      strategy: "RAW", as_of_date: "2026-08-28", top_k: 3,
    },
    grounding: {
      ...lifecycle, id: `grounding-${scenario}`, retrieval_run_id: `retrieval-${scenario}`,
      citation_pack_id: `pack-${scenario}`,
    },
    policy: {
      ...lifecycle, id: `policy-${scenario}`, analysis_run_id: `text-${scenario}`,
      summary_status: summary, as_of_date: "2026-08-28",
      rule_set: { name: "csight_commerce_defect_ops", version: "2026.08-demo", hash: "fixture-policy-hash" },
    },
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
    extraction_result: null, extraction_result_v2: null, vision_results: [{
      evidence_id: `evidence-${scenario}`,
      result: {
        schema_version: "1.0", provider_name: "remote_vision", model_name: "spoofed-e3-name",
        model_version: "unknown", model_revision: null, dataset_version: null,
        taxonomy_version: "unknown", threshold_version: "unknown", preprocess_version: "unknown",
        postprocess_version: "unknown", detections: [{ label: "CRACK", confidence: 0.99 }],
        image_assessment: {
          assessment_type: "ANY_DEFECT", model_output_name: "defect", score: 0.99,
          threshold: 0.8984375, threshold_operator: "GREATER_THAN_OR_EQUAL",
          outcome: "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
        },
      },
    }], failed_stages: ["VISION_ANALYSIS"],
  };
}

async function json(route: Route, value: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(value) });
}

export async function installApi(page: Page, scenario: DemoScenario) {
  let role = "REVIEWER";
  let activeTask = scenario === "validated"
    ? { ...taskFor(scenario), status: "PENDING", current_assignee_id: null, version: 1, resolved_at: null }
    : taskFor(scenario);
  let quickReportReady = scenario !== "validated";
  const policyRuns = policyRunsFor(scenario);
  const textRun = textRunFor(scenario);
  await page.route("**/auth/session", (route) => json(route, {
    error: { code: "AUTHENTICATION_REQUIRED", message: "No OIDC fixture session." },
  }, 401));
  await page.route("**/auth/capabilities", (route) => json(route, {
    oidc_enabled: false, legacy_password_enabled: true,
  }));
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
    if (path === "/api/v1/operator/cases") {
      const item = caseFor(scenario);
      const unassigned = ["PENDING", "ESCALATED"].includes(activeTask.status) && !activeTask.current_assignee_id;
      const waiting = activeTask.status === "WAITING_FOR_EVIDENCE";
      const complete = activeTask.status === "RESOLVED" && quickReportReady;
      const assignedToMe = !complete && activeTask.current_assignee_id === "user-1";
      const view = url.searchParams.get("view") ?? "all";
      const visible = view === "all"
        || (view === "my" && assignedToMe)
        || (view === "unassigned" && unassigned)
        || (view === "urgent" && activeTask.priority === "CRITICAL")
        || (view === "waiting_evidence" && waiting)
        || (view === "complete" && complete);
      return json(route, {
        items: visible ? [{
          case_id: item.case_id, case_status: item.status, order_ref: item.order_ref, product_ref: item.product_ref,
          requested_action: item.requested_action, inquiry_preview: item.customer_message.slice(0, 160), created_at: item.created_at, updated_at: activeTask.updated_at,
          review_task_id: activeTask.id, review_status: activeTask.status, review_priority: activeTask.priority,
          assignee_id: activeTask.current_assignee_id, assignment_version: activeTask.current_assignee_id ? 1 : 0, resolution_status: complete ? "ACTION_DRY_RUN_VALIDATED" : null,
          report_id: complete ? "report-1" : null, report_generated_at: complete ? now : null,
        }] : [],
        counts: { all: 1, my: assignedToMe ? 1 : 0, unassigned: unassigned ? 1 : 0, urgent: activeTask.priority === "CRITICAL" ? 1 : 0, waiting_evidence: waiting ? 1 : 0, complete: complete ? 1 : 0 },
        next_cursor: null,
      });
    }
    if (path === "/api/v1/human-review-assignees") return json(route, { items: [{ user_id: "user-1", display_name: "관리자", email: "admin@demo.test", roles: ["ADMIN"] }] });
    if (path === `/api/v1/cases/case-${scenario}/assignment` && request.method() === "POST") {
      const body = request.postDataJSON() as { assignee_id: string; expected_version: number; rationale: string };
      activeTask.current_assignee_id = body.assignee_id;
      if (activeTask.status === "PENDING") activeTask.status = "CLAIMED";
      activeTask.version += 1;
      activeTask.updated_at = now;
      return json(route, {
        case_id: `case-${scenario}`, current_assignee_id: body.assignee_id,
        version: body.expected_version + 1, assigned_by: "user-1",
        assignment_type: body.expected_version === 0 ? "ADMIN_ASSIGNMENT" : "ADMIN_REASSIGNMENT",
        rationale: body.rationale, assigned_at: now,
      });
    }
    if (path === "/api/v1/operator/reviews") {
      const item = caseFor(scenario);
      const assignedToMe = ["CLAIMED", "WAITING_FOR_EVIDENCE"].includes(activeTask.status) && activeTask.current_assignee_id === "user-1";
      const unassigned = ["PENDING", "ESCALATED"].includes(activeTask.status) && !activeTask.current_assignee_id;
      const waiting = activeTask.status === "WAITING_FOR_EVIDENCE";
      const complete = activeTask.status === "RESOLVED";
      const view = url.searchParams.get("view") ?? "all";
      const visible = view === "all"
        || (view === "my" && assignedToMe)
        || (view === "unassigned" && unassigned)
        || (view === "urgent" && activeTask.priority === "CRITICAL")
        || (view === "waiting_evidence" && waiting)
        || (view === "complete" && complete);
      return json(route, {
        items: visible ? [{
          review_task_id: activeTask.id, case_id: activeTask.case_id, case_status: item.status,
          order_ref: item.order_ref, product_ref: item.product_ref, requested_action: item.requested_action, inquiry_preview: item.customer_message.slice(0, 160),
          task_type: activeTask.task_type, priority: activeTask.priority, status: activeTask.status,
          assignee_id: activeTask.current_assignee_id, version: activeTask.version, created_at: activeTask.created_at,
          updated_at: activeTask.updated_at, resolution_status: null, report_id: null, report_generated_at: null,
        }] : [],
        counts: { all: 1, my: activeTask.current_assignee_id === "user-1" ? 1 : 0, unassigned: activeTask.current_assignee_id ? 0 : 1, urgent: activeTask.priority === "CRITICAL" ? 1 : 0, waiting_evidence: activeTask.status === "WAITING_FOR_EVIDENCE" ? 1 : 0, complete: activeTask.status === "RESOLVED" ? 1 : 0 },
        next_cursor: null,
      });
    }
    if (path === "/api/v1/cases" && request.method() === "GET") {
      const item = caseFor(scenario);
      const { customer_message: _message, attributes: _attributes, created_by: _createdBy, evidence: _evidence, status_history: _history, latest_analysis_run: _latest, ...summary } = item;
      return json(route, { items: [summary], page: 1, page_size: 100, total: 1 });
    }
    if (path === `/api/v1/cases/case-${scenario}/human-review-tasks`) return json(route, { items: [activeTask] });
    if (path === `/api/v1/cases/case-${scenario}/workflow-snapshot`) return json(route, {
      case_id: `case-${scenario}`, case_status: "REVIEW_PENDING", terminal: false,
      degraded: scenario === "vision-timeout", retry_at: null, last_good: "HUMAN_REVIEW",
      correlation_id: `correlation-${scenario}`, stages: [],
      analysis: {
        run_id: `text-${scenario}`, status: "SUCCEEDED", started_at: now, completed_at: now,
        failure_code: null, correlation_id: `correlation-${scenario}`,
      },
      policy_retrieval: {
        run_id: `retrieval-${scenario}`, status: "SUCCEEDED", started_at: now, completed_at: now,
        failure_code: null, correlation_id: `correlation-${scenario}`,
      },
      grounded_explanation: {
        run_id: `grounding-${scenario}`, status: "SUCCEEDED", started_at: now, completed_at: now,
        failure_code: null, correlation_id: `correlation-${scenario}`,
      },
      policy_evaluation: {
        run_id: `policy-${scenario}`, status: "SUCCEEDED", started_at: now, completed_at: now,
        failure_code: null, correlation_id: `correlation-${scenario}`,
      },
      review: {
        run_id: activeTask.id, status: activeTask.status, started_at: now,
        completed_at: activeTask.resolved_at, failure_code: null,
        correlation_id: `correlation-${scenario}`,
      },
      resolution: null, report: null,
    });
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
    if (path === `/api/v1/cases/case-${scenario}/review-report`) {
      if (!quickReportReady) return json(route, { error: { code: "REVIEW_REPORT_NOT_FOUND", message: "Report is still being generated." } }, 404);
      return json(route, {
        schema_version: "review_report/1.0.0", report_id: "96f0b4f6-a24a-4f0c-9965-613c4c15c428", case_id: `case-${scenario}`,
        resolution_id: `resolution-${scenario}`, resolution_version: 2, terminal_event_id: "resolution-event-1",
        case_snapshot: {
          order_ref: `ORD-${scenario.toUpperCase()}`,
          product_ref: `SKU-${scenario.toUpperCase()}`,
          requested_action: scenario === "validated" ? "REPAIR" : "REFUND",
          created_at: now,
        },
        analysis_snapshot: { status: "SUCCEEDED" }, policy_snapshot: {
          summary_status: "REQUIRES_HUMAN_REVIEW", rule_set_id: "CSCC-DEFECT-OPS",
          rule_set_version: "2026.08-demo", as_of_date: "2026-08-28",
        },
        review_snapshot: {
          decision_type: scenario === "validated" ? "APPROVE_REPAIR" : "APPROVE_REFUND",
          rationale: "정책 근거와 고객이 제출한 주문·이미지 정보를 담당자가 확인했습니다.",
          decided_by: "user-1", decided_at: now, actor_type: "AUTHENTICATED_HUMAN",
          decision_hash: "decision-hash", packet_hash: "packet-hash",
        },
        resolution_snapshot: {
          status: scenario === "validated" ? "ACTION_DRY_RUN_VALIDATED" : "ACTION_NEEDS_INPUT",
          missing_fields: scenario === "needs-input" ? ["amount", "currency"] : [], invalid_fields: [], terminal_event_at: now,
        },
        dry_run_snapshot: scenario === "validated"
          ? { mode: "DRY_RUN", side_effects_performed: false }
          : { intent: null, result: null },
        qualification_snapshot: { scope: "SYNTHETIC_DEMO" }, data_scope: { real_customer_data: false },
        generated_at: now, content_hash: "b".repeat(64),
      });
    }
    if (path === `/api/v1/cases/case-${scenario}/analysis-runs` && request.method() === "GET") {
      const items = scenario === "vision-timeout" ? [textRun, analysisDetail(scenario).run] : [textRun];
      return json(route, { items, page: 1, page_size: 100, total: items.length });
    }
    if (path === `/api/v1/cases/case-${scenario}/analysis-runs/text-${scenario}`) return json(route, {
      run: textRun, stages: [], extraction_result: null,
      extraction_result_v2: { requested_actions: [], system_missing_information: [] },
      vision_results: [], failed_stages: [],
    });
    if (path === `/api/v1/cases/case-${scenario}/analysis-runs/vision-${scenario}`) return json(route, analysisDetail(scenario));
    if (path === `/api/v1/cases/case-${scenario}/policy-retrieval-runs`) return json(route, { items: [policyRuns.retrieval] });
    if (path === `/api/v1/cases/case-${scenario}/grounded-explanation-runs`) return json(route, { items: [policyRuns.grounding] });
    if (path === `/api/v1/cases/case-${scenario}/policy-evaluation-runs`) return json(route, { items: [policyRuns.policy] });
    if (path === `/api/v1/cases/case-${scenario}/policy-retrieval-runs/retrieval-${scenario}`) return json(route, {
      run: policyRuns.retrieval, query_plan: null,
      retrieval_profile: { base_mode: "HYBRID", reranker_enabled: false },
      hits: [{
        rank: 1, clause_id: "CSCC-OPS-4.2", document_id: "csight-commerce-defect-ops",
        document_version: "2026.08-demo",
      }],
    });
    if (path === `/api/v1/cases/case-${scenario}/grounded-explanation-runs/grounding-${scenario}`) return json(route, {
      run: policyRuns.grounding,
      citation_pack: { citations: [{
        citation_id: `citation-${scenario}`, rank: 1, policy_clause_id: "CSCC-OPS-4.2",
        document_id: "csight-commerce-defect-ops", document_version: "2026.08-demo",
        title: "CSight Commerce 상품 하자 반품·교환 운영정책",
        section_path: ["4. 상품 하자", "4.2 검토 및 처리"], clause_type: "REVIEW_GUIDANCE",
        text: "상품 하자 문의는 주문 정보와 제출된 증거를 확인한 뒤 담당자의 검토를 거쳐 반품·교환·수리 권고 후보로 분류한다.",
      }] },
      explanation: { summary: "가상 사내 운영정책의 상품 하자 조항이 현재 문의 검토를 뒷받침합니다." },
      structural_validation: { valid: true }, semantic_evaluation_status: "SKIPPED",
    });
    if (path === `/api/v1/cases/case-${scenario}/policy-evaluation-runs/policy-${scenario}`) return json(route, {
      run: policyRuns.policy,
      input_qualification: { source_scope: "SYNTHETIC_REFERENCE", vision_linkage: "NOT_LINKED" },
      rule_results: [{
        rule_id: "CSCC-DEFECT-REVIEW-04", rule_version: "1.0.0", status: "MATCHED",
        condition_results: [], effects: [{ type: "REQUIRE_HUMAN_REVIEW" }],
        source_clause_ids: ["CSCC-OPS-4.2"],
      }],
    });
    if (path === `/api/v1/cases/case-${scenario}/evidence/evidence-${scenario}/content`) {
      return route.fulfill({ status: 200, contentType: "image/png", headers: { "Cache-Control": "no-store" }, body: previewPng });
    }
    if (path === `/api/v1/cases/case-${scenario}`) return json(route, caseFor(scenario));
    if (path === "/api/v1/human-review-tasks") return json(route, { items: [activeTask] });
    if (path === `/api/v1/human-review-tasks/task-${scenario}`) return json(route, reviewDetail(scenario, activeTask));
    if (path.startsWith(`/api/v1/human-review-tasks/task-${scenario}/`) && request.method() === "POST") {
      if (path.endsWith("/claim")) {
        const body = request.postDataJSON() as { expected_version?: number };
        if (scenario === "validated" && body.expected_version !== 1) {
          return json(route, { error: { code: "FIXTURE_CLAIM_VERSION", message: "Quick review must claim version 1." } }, 422);
        }
        activeTask = { ...activeTask, status: "CLAIMED", current_assignee_id: "user-1", version: activeTask.version + 1 };
        return json(route, { task: activeTask, decision: null });
      }
      if (path.endsWith("/resolve")) {
        const body = request.postDataJSON() as { expected_version?: number; decision?: string; reason_codes?: string[]; basis?: Array<{ type?: string; reference_id?: string }> };
        if (scenario === "validated" && (
          body.expected_version !== 2
          || body.decision !== "APPROVE_REPAIR"
          || body.reason_codes?.[0] !== "POLICY_CONDITION_MET"
          || body.basis?.[0]?.type !== "POLICY_RULE_RESULT"
          || body.basis?.[1]?.type !== "POLICY_CITATION"
        )) return json(route, { error: { code: "FIXTURE_QUICK_RESOLVE_BODY", message: "Quick review resolve contract mismatch." } }, 422);
        activeTask = { ...activeTask, status: "RESOLVED", current_assignee_id: null, version: activeTask.version + 1, resolved_at: now };
        quickReportReady = true;
        return json(route, { task: activeTask, decision: { decision: body.decision ?? "APPROVE_REPAIR", actor_id: "user-1" } });
      }
      return json(route, { task: activeTask, decision: null });
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
