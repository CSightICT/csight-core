import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import type { AnalysisRun } from "../api/contracts";
import { tokenVault } from "../auth/tokenVault";
import { server } from "../test/server";
import { CaseWorkspacePage } from "./CaseWorkspacePage";

const now = "2026-08-28T00:00:00Z";

function run(id: string, pipeline: string, version: string, requestedAt: string): AnalysisRun {
  return {
    analysis_run_id: id,
    tenant_id: "tenant-1",
    case_id: "case-1",
    pipeline,
    pipeline_version: version,
    trigger: "USER_REQUEST",
    status: "SUCCEEDED",
    requested_by: "user-1",
    requested_at: requestedAt,
    started_at: requestedAt,
    completed_at: requestedAt,
    failure: null,
    created_at: requestedAt,
    updated_at: requestedAt,
  };
}

const textOld = run("text-old", "product_defect_text_extraction", "2.0.0", "2026-08-27T23:00:00Z");
const textLatest = run("text-latest", "product_defect_text_extraction", "2.0.0", now);
const visionOld = run("vision-old", "product_defect_multimodal_analysis", "1.0.0", "2026-08-27T22:00:00Z");
const visionLatest = run("vision-latest", "product_defect_multimodal_analysis", "1.0.0", "2026-08-27T23:59:00Z");

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  tokenVault.clear();
  sessionStorage.clear();
});
afterAll(() => server.close());

describe("CaseWorkspacePage", () => {
  it("recovers the latest Text v2 and Vision runs from the server in a cold session", async () => {
    let startCalls = 0;
    const lifecycle = {
      case_id: "case-1", status: "SUCCEEDED", correlation_id: "correlation-1",
      created_at: "2026-08-27T23:30:00Z", started_at: "2026-08-27T23:30:00Z",
      completed_at: "2026-08-27T23:31:00Z", failure_code: null, failure_message: null,
    };
    const retrievalComplete = {
      ...lifecycle, id: "retrieval-complete", analysis_run_id: "text-latest", strategy: "RAW",
      as_of_date: "2026-08-28", top_k: 3,
    };
    const retrievalNewIncomplete = {
      ...lifecycle, id: "retrieval-new-incomplete", analysis_run_id: "text-latest", strategy: "RAW",
      as_of_date: "2026-08-28", top_k: 3, created_at: "2026-08-27T23:50:00Z",
    };
    const groundingComplete = {
      ...lifecycle, id: "grounding-complete", retrieval_run_id: "retrieval-complete",
      citation_pack_id: "pack-complete", created_at: "2026-08-27T23:32:00Z",
    };
    const policyLatest = {
      ...lifecycle, id: "policy-latest", analysis_run_id: "text-latest",
      summary_status: "REVIEW_REQUIRED",
      rule_set: { name: "synthetic_policy", version: "1.0.0", hash: "hash-1" },
      as_of_date: "2026-08-28", created_at: "2026-08-27T23:33:00Z",
    };
    const policyOld = {
      ...policyLatest, id: "policy-old", created_at: "2026-08-27T22:33:00Z",
    };
    server.use(
      http.get("/api/v1/cases/case-1/analysis-runs", () => HttpResponse.json({
        items: [visionOld, textLatest, textOld, visionLatest], page: 1, page_size: 100, total: 4,
      })),
      http.post("/api/v1/cases/case-1/analysis-runs", () => {
        startCalls += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
      http.get("/api/v1/cases/case-1/policy-retrieval-runs", () => HttpResponse.json({
        items: [retrievalNewIncomplete, retrievalComplete],
      })),
      http.get("/api/v1/cases/case-1/grounded-explanation-runs", () => HttpResponse.json({
        items: [groundingComplete],
      })),
      http.get("/api/v1/cases/case-1/policy-evaluation-runs", () => HttpResponse.json({
        items: [policyOld, policyLatest],
      })),
      http.post("/api/v1/cases/case-1/policy-retrieval-runs", () => {
        startCalls += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
      http.post("/api/v1/cases/case-1/grounded-explanation-runs", () => {
        startCalls += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
      http.post("/api/v1/cases/case-1/policy-evaluation-runs", () => {
        startCalls += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
      http.get("/api/v1/cases/case-1/analysis-runs/text-latest", () => HttpResponse.json({
        run: textLatest,
        stages: [{
          stage_run_id: "text-stage", stage_type: "LLM_EXTRACTION", status: "SUCCEEDED",
          model_name: "mock-llm", model_version: "1.0", prompt_version: "2.0.0", attempt_count: 1,
        }],
        extraction_result: null, extraction_result_v2: {}, vision_results: [], failed_stages: [],
      })),
      http.get("/api/v1/cases/case-1/analysis-runs/vision-latest", () => HttpResponse.json({
        run: visionLatest,
        stages: [{
          stage_run_id: "vision-stage", stage_type: "VISION_ANALYSIS", status: "SUCCEEDED",
          model_name: "csight-dinov2-vits14-kaputt-binary", model_version: "e3-epoch10-20260827",
          prompt_version: "not-applicable", attempt_count: 1,
        }],
        extraction_result: null,
        extraction_result_v2: null,
        vision_results: [{
          evidence_id: "evidence-1",
          result: {
            schema_version: "1.0",
            provider_name: "remote_vision",
            model_name: "csight-dinov2-vits14-kaputt-binary",
            model_version: "e3-epoch10-20260827",
            model_revision: "49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e",
            dataset_version: null,
            taxonomy_version: "csight-any-defect-assessment-v1",
            threshold_version: "1.0",
            preprocess_version: "1.0",
            postprocess_version: "sigmoid-any-defect-v1",
            detections: [],
            image_assessment: {
              assessment_type: "ANY_DEFECT",
              model_output_name: "defect",
              score: 0.999428927898407,
              threshold: 0.8984375,
              threshold_operator: "GREATER_THAN_OR_EQUAL",
              outcome: "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
            },
          },
        }],
        failed_stages: [],
      })),
      http.get("/api/v1/cases/case-1/policy-retrieval-runs/retrieval-complete", () => HttpResponse.json({
        run: retrievalComplete,
        query_plan: null,
        retrieval_profile: { base_mode: "HYBRID", reranker_enabled: false },
        hits: [{
          rank: 1, clause_id: "clause-1", document_id: "policy-1", document_version: "2026.08",
        }],
      })),
      http.get("/api/v1/cases/case-1/grounded-explanation-runs/grounding-complete", () => HttpResponse.json({
        run: groundingComplete,
        citation_pack: { citations: [{
          citation_id: "citation-1", rank: 1, policy_clause_id: "clause-1", document_id: "policy-1",
          document_version: "2026.08", title: "내부 합성 교환 정책", section_path: ["결함", "교환"],
          clause_type: "ELIGIBILITY", text: "결함 증거와 주문 정보를 상담원이 함께 확인합니다.",
        }] },
        explanation: {}, structural_validation: {}, semantic_evaluation_status: "SKIPPED",
      })),
      http.get("/api/v1/cases/case-1/policy-evaluation-runs/policy-latest", () => HttpResponse.json({
        run: policyLatest,
        input_qualification: { evidence_scope: "ADVISORY_ONLY" },
        rule_results: [],
      })),
      http.get("/api/v1/cases/case-1/human-review-tasks", () => HttpResponse.json({ items: [
        {
          id: "review-stale", case_id: "case-1", policy_evaluation_run_id: "policy-old",
          task_type: "STALE_SAFETY_REVIEW", priority: "CRITICAL", status: "CLAIMED",
          current_assignee_id: "user-old", version: 9, mapping_rule_name: "synthetic_mapping",
          mapping_rule_version: "1.0.0", created_at: now, updated_at: now, resolved_at: null,
        },
        {
          id: "review-1", case_id: "case-1", policy_evaluation_run_id: "policy-latest",
          task_type: "POLICY_REVIEW", priority: "NORMAL", status: "PENDING",
          current_assignee_id: null, version: 1, mapping_rule_name: "synthetic_mapping",
          mapping_rule_version: "1.0.0", created_at: now, updated_at: now, resolved_at: null,
        },
      ] })),
      http.get("/api/v1/cases/case-1/resolution/events", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-1/external-action-intents", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-1/resolution", () => HttpResponse.json({
        detail: { code: "CASE_RESOLUTION_NOT_FOUND", message: "No resolution" },
      }, { status: 404 })),
      http.get("/api/v1/cases/case-1", () => HttpResponse.json({
        case_id: "case-1", tenant_id: "tenant-1", domain_type: "product_defect_cs", status: "RECEIVED",
        order_ref: "TOP100-RANK-054", product_ref: "KAPUTT-PLASTIC-HARD-PROXY", requested_action: "UNSPECIFIED",
        created_at: now, updated_at: now, customer_message: "내부 시뮬레이션 이미지입니다.", attributes: {
          demo_image_observation: "본체 표면과 결합부 외관이 촬영되어 있습니다.",
          demo_claim_boundary: "CUSTOMER_STATEMENT_ONLY_FOR_NON_VISIBLE_FACTS",
          realistic_demo: {
            schema_version: "2.0", dataset_id: "realistic-internal-demo-v2",
            scenario_scope: "INTERNAL_CURATED_ECOMMERCE_INQUIRY_6_DEFECT_4_BELOW_THRESHOLD",
            narrative_revision: "VISUAL_ALIGNED_R1",
            source_grade: "KAPUTT_SELECTED_CORRECT_POSITIVE",
            selection_bias: "POSITIVE_ONLY_CORRECT_ONLY_HIGH_CONFIDENCE",
            rights_status: "INTERNAL_RESTRICTED_PROVENANCE_UNVERIFIED",
            policy_input_linkage: "NOT_LINKED_TO_POLICY_INPUT",
          },
        },
        created_by: "user-1", evidence: [], status_history: [], latest_analysis_run: visionLatest,
      })),
    );
    tokenVault.set("test-token", 600);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/cases/case-1"]}><Routes>
      <Route path="/cases/:caseId" element={<CaseWorkspacePage />} />
    </Routes></MemoryRouter></QueryClientProvider>);

    expect(await screen.findByTestId("review-workbench")).toBeVisible();
    expect(screen.getByRole("heading", { name: "문의 내용" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "이미지 근거" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "정책 기반 권고" })).toBeVisible();
    expect(screen.getByTestId("fictional-inquiry-badge")).toHaveTextContent("가상 문의 · PoC");
    expect(screen.getByTestId("image-observation-boundary")).toHaveTextContent("사진에서 확인되는 범위");
    expect(screen.getByTestId("image-observation-boundary")).toHaveTextContent("본체 표면과 결합부 외관이 촬영되어 있습니다.");
    expect(screen.getByTestId("image-observation-boundary")).toHaveTextContent("비가시 정보는 고객 진술이며 Vision 근거가 아닙니다");
    expect(screen.getAllByText("가상 사내 정책 · PoC 전용").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByRole("heading", { name: "상담 내용" })).not.toBeInTheDocument();
    expect(await screen.findByTestId("text-analysis-summary")).toHaveTextContent("text-latest");
    expect(await screen.findByTestId("vision-result")).toHaveTextContent("99.94%");
    expect(screen.getByTestId("vision-result")).toHaveTextContent("이미지 이상 가능성");
    expect(screen.getByTestId("vision-result")).toHaveTextContent("E3 Runtime identity 일치");
    expect(screen.getByText("원격 추론 · 제품 적격성 미확인")).not.toBeVisible();
    await userEvent.click(screen.getByText("모델 및 검증 범위"));
    expect(screen.getByText("원격 추론 · 제품 적격성 미확인")).toBeVisible();
    expect(screen.getByText(/고정된 E3 Runtime identity와 일치하지만 제품 적격성은 별도 external gate/)).toBeVisible();
    expect(screen.queryByText("Mock qualification")).not.toBeInTheDocument();
    expect(await screen.findByText("내부 합성 교환 정책")).toBeVisible();
    expect(screen.getByText("결함 증거와 주문 정보를 상담원이 함께 확인합니다.")).toBeVisible();
    expect(screen.getByText(/문서 버전 2026.08/)).toBeVisible();
    expect(screen.getByText("POLICY_REVIEW")).toBeVisible();
    expect(screen.getByText("NORMAL")).toBeVisible();
    expect(screen.queryByText("STALE_SAFETY_REVIEW")).not.toBeInTheDocument();
    expect(screen.queryByText("CRITICAL")).not.toBeInTheDocument();
    expect(screen.getByText("독립 실행 연결 경계")).not.toBeVisible();
    await userEvent.click(screen.getByText("운영 정보 · 분석 진행과 실행 연결"));
    expect(screen.getByText("독립 실행 연결 경계")).toBeVisible();
    expect(screen.getByText(/하나의 검증된 exact chain으로 단정하지 않습니다/)).toBeVisible();
    expect(screen.getByText("제공되지 않음 · exact chain 미확정")).toBeVisible();
    expect(screen.getByText("policy-latest")).toBeVisible();
    expect(screen.queryByText("policy-old")).not.toBeInTheDocument();
    expect(screen.getByText("담당자 확인이 필요합니다")).toBeVisible();
    expect(screen.getByRole("link", { name: "검토 진행하기" })).toBeVisible();
    await waitFor(() => expect(JSON.parse(sessionStorage.getItem("csight.workflow.v1") ?? "{}")).toMatchObject({
      caseId: "case-1", analysisV2RunId: "text-latest", visionRunId: "vision-latest",
      retrievalRunId: "retrieval-complete", groundingRunId: "grounding-complete",
      policyEvaluationRunId: "policy-latest",
    }));
    expect(startCalls).toBe(0);
  });

  it("recovers a queued/running policy run set and never posts duplicate active stages", async () => {
    let startCalls = 0;
    let retrievalLoads = 0;
    let groundingLoads = 0;
    let policyLoads = 0;
    let reviewLoads = 0;
    const lifecycle = {
      case_id: "case-1", correlation_id: "correlation-active", created_at: now,
      started_at: now, completed_at: null, failure_code: null, failure_message: null,
    };
    const retrievalActive = {
      ...lifecycle, id: "retrieval-active", analysis_run_id: "text-latest", strategy: "RAW",
      status: "QUEUED", as_of_date: "2026-08-28", top_k: 3,
    };
    const groundingActive = {
      ...lifecycle, id: "grounding-active", retrieval_run_id: "retrieval-active",
      citation_pack_id: "pack-active", status: "RUNNING",
    };
    const policyActive = {
      ...lifecycle, id: "policy-active", analysis_run_id: "text-latest", status: "RUNNING",
      summary_status: null, rule_set: { name: "synthetic_policy", version: "1.0.0", hash: "hash-active" },
      as_of_date: "2026-08-28",
    };
    const staleReview = {
      id: "review-stale", case_id: "case-1", policy_evaluation_run_id: "policy-old",
      task_type: "STALE_REVIEW", priority: "CRITICAL", status: "CLAIMED",
      current_assignee_id: "user-old", version: 4, mapping_rule_name: "synthetic_mapping",
      mapping_rule_version: "1.0.0", created_at: now, updated_at: now, resolved_at: null,
    };
    const currentReview = {
      ...staleReview, id: "review-active", policy_evaluation_run_id: "policy-active",
      task_type: "POLICY_REVIEW", priority: "NORMAL", status: "PENDING",
      current_assignee_id: null, version: 1,
    };
    const succeeded = <T extends { status: string; completed_at: string | null }>(value: T): T => ({
      ...value, status: "SUCCEEDED", completed_at: now,
    });

    server.use(
      http.get("/api/v1/cases/case-1/analysis-runs", () => HttpResponse.json({
        items: [textLatest], page: 1, page_size: 100, total: 1,
      })),
      http.get("/api/v1/cases/case-1/policy-retrieval-runs", () => HttpResponse.json({ items: [retrievalActive] })),
      http.get("/api/v1/cases/case-1/grounded-explanation-runs", () => HttpResponse.json({ items: [groundingActive] })),
      http.get("/api/v1/cases/case-1/policy-evaluation-runs", () => HttpResponse.json({ items: [policyActive] })),
      http.get("/api/v1/cases/case-1/analysis-runs/text-latest", () => HttpResponse.json({
        run: textLatest, stages: [], extraction_result: null, extraction_result_v2: {},
        vision_results: [], failed_stages: [],
      })),
      http.get("/api/v1/cases/case-1/policy-retrieval-runs/retrieval-active", () => {
        retrievalLoads += 1;
        const runValue = retrievalLoads === 1 ? retrievalActive : succeeded(retrievalActive);
        return HttpResponse.json({
          run: runValue, query_plan: null,
          retrieval_profile: { base_mode: "HYBRID", reranker_enabled: false }, hits: [],
        });
      }),
      http.get("/api/v1/cases/case-1/grounded-explanation-runs/grounding-active", () => {
        groundingLoads += 1;
        const runValue = groundingLoads === 1 ? groundingActive : succeeded(groundingActive);
        return HttpResponse.json({
          run: runValue, citation_pack: { citations: [] }, explanation: null,
          structural_validation: null, semantic_evaluation_status: "SKIPPED",
        });
      }),
      http.get("/api/v1/cases/case-1/policy-evaluation-runs/policy-active", () => {
        policyLoads += 1;
        const runValue = policyLoads === 1 ? policyActive : succeeded(policyActive);
        return HttpResponse.json({ run: runValue, input_qualification: {}, rule_results: [] });
      }),
      http.get("/api/v1/cases/case-1/human-review-tasks", () => {
        reviewLoads += 1;
        return HttpResponse.json({ items: reviewLoads === 1 ? [staleReview] : [staleReview, currentReview] });
      }),
      http.post("/api/v1/cases/case-1/analysis-runs", () => {
        startCalls += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
      http.post("/api/v1/cases/case-1/policy-retrieval-runs", () => {
        startCalls += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
      http.post("/api/v1/cases/case-1/grounded-explanation-runs", () => {
        startCalls += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
      http.post("/api/v1/cases/case-1/policy-evaluation-runs", () => {
        startCalls += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
      http.get("/api/v1/cases/case-1/resolution/events", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-1/external-action-intents", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-1/resolution", () => HttpResponse.json({
        detail: { code: "CASE_RESOLUTION_NOT_FOUND", message: "No resolution" },
      }, { status: 404 })),
      http.get("/api/v1/cases/case-1", () => HttpResponse.json({
        case_id: "case-1", tenant_id: "tenant-1", domain_type: "product_defect_cs", status: "OPEN",
        order_ref: "ORD-ACTIVE", product_ref: "SKU-ACTIVE", requested_action: "UNSPECIFIED",
        created_at: now, updated_at: now, customer_message: "진행 중 복구", attributes: {},
        created_by: "user-1", evidence: [], status_history: [], latest_analysis_run: textLatest,
      })),
    );
    tokenVault.set("test-token", 600);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/cases/case-1"]}><Routes>
      <Route path="/cases/:caseId" element={<CaseWorkspacePage />} />
    </Routes></MemoryRouter></QueryClientProvider>);

    expect(await screen.findByText("서버의 진행 중 실행 복구")).toBeVisible();
    expect(screen.getByText("담당자 검토를 준비하고 있습니다")).toBeVisible();
    expect(screen.queryByText("STALE_REVIEW")).not.toBeInTheDocument();
    await waitFor(() => expect(JSON.parse(sessionStorage.getItem("csight.workflow.v1") ?? "{}")).toMatchObject({
      caseId: "case-1", analysisV2RunId: "text-latest", retrievalRunId: "retrieval-active",
      groundingRunId: "grounding-active", policyEvaluationRunId: "policy-active",
    }));
    const activeButton = screen.getByRole("button", { name: "진행 상태 확인" });
    await userEvent.click(activeButton);
    await waitFor(() => expect(screen.getByRole("link", { name: "검토 진행하기" })).toBeVisible());
    expect(await screen.findByText("POLICY_REVIEW")).toBeVisible();
    expect(screen.queryByText("STALE_REVIEW")).not.toBeInTheDocument();
    expect(startCalls).toBe(0);
  });

  it("resets a failed Text checkpoint and retries with a new idempotency while preserving Vision", async () => {
    const textFailed = {
      ...run("text-failed", "product_defect_text_extraction", "2.0.0", "2026-08-28T01:00:00Z"),
      status: "FAILED",
      failure: { code: "TEXT_PROVIDER_FAILED", retryable: true },
    };
    const visionGood = run(
      "vision-good",
      "product_defect_multimodal_analysis",
      "1.0.0",
      "2026-08-28T01:30:00Z",
    );
    const textRetryQueued = {
      ...run("text-retry", "product_defect_text_extraction", "2.0.0", "2026-08-28T02:00:00Z"),
      status: "QUEUED",
      started_at: null,
      completed_at: null,
    };
    const textRetrySucceeded = {
      ...textRetryQueued, status: "SUCCEEDED", started_at: now, completed_at: now,
    };
    let retryCalls = 0;
    let retryKey: string | null = null;
    let retryBody: unknown;
    sessionStorage.setItem("csight.workflow.v1", JSON.stringify({
      caseId: "case-1",
      analysisV2RunId: "text-failed",
      visionRunId: "vision-good",
      retrievalRunId: "retrieval-old",
      groundingRunId: "grounding-old",
      policyEvaluationRunId: "policy-old",
      idempotencyKeys: {
        analysisV2: "text-key-old", vision: "vision-key-stable", retrieval: "retrieval-key-old",
        grounding: "grounding-key-old", policy: "policy-key-old",
      },
    }));
    const missingDetail = { detail: { code: "RUN_NOT_FOUND", message: "Old downstream detail" } };
    server.use(
      http.get("/api/v1/cases/case-1/analysis-runs/text-failed", () => HttpResponse.json({
        run: textFailed, stages: [], extraction_result: null, extraction_result_v2: null,
        vision_results: [], failed_stages: ["LLM_EXTRACTION"],
      })),
      http.get("/api/v1/cases/case-1/analysis-runs/vision-good", () => HttpResponse.json({
        run: visionGood, stages: [], extraction_result: null, extraction_result_v2: null,
        vision_results: [], failed_stages: [],
      })),
      http.post("/api/v1/cases/case-1/analysis-runs", async ({ request }) => {
        retryCalls += 1;
        retryKey = request.headers.get("Idempotency-Key");
        retryBody = await request.json();
        return HttpResponse.json(textRetryQueued, { status: 202 });
      }),
      http.get("/api/v1/cases/case-1/analysis-runs/text-retry", () => HttpResponse.json({
        run: textRetrySucceeded, stages: [], extraction_result: null, extraction_result_v2: {},
        vision_results: [], failed_stages: [],
      })),
      http.get("/api/v1/cases/case-1/policy-retrieval-runs/retrieval-old", () => HttpResponse.json(missingDetail, { status: 404 })),
      http.get("/api/v1/cases/case-1/grounded-explanation-runs/grounding-old", () => HttpResponse.json(missingDetail, { status: 404 })),
      http.get("/api/v1/cases/case-1/policy-evaluation-runs/policy-old", () => HttpResponse.json(missingDetail, { status: 404 })),
      http.get("/api/v1/cases/case-1/policy-retrieval-runs", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-1/grounded-explanation-runs", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-1/policy-evaluation-runs", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-1/human-review-tasks", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-1/resolution/events", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-1/external-action-intents", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-1/resolution", () => HttpResponse.json({
        detail: { code: "CASE_RESOLUTION_NOT_FOUND", message: "No resolution" },
      }, { status: 404 })),
      http.get("/api/v1/cases/case-1", () => HttpResponse.json({
        case_id: "case-1", tenant_id: "tenant-1", domain_type: "product_defect_cs", status: "OPEN",
        order_ref: "ORD-FAILED", product_ref: "SKU-FAILED", requested_action: "UNSPECIFIED",
        created_at: now, updated_at: now, customer_message: "실패 실행 재시도", attributes: {},
        created_by: "user-1", evidence: [], status_history: [], latest_analysis_run: textFailed,
      })),
    );
    tokenVault.set("test-token", 600);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/cases/case-1"]}><Routes>
      <Route path="/cases/:caseId" element={<CaseWorkspacePage />} />
    </Routes></MemoryRouter></QueryClientProvider>);

    expect(await screen.findByRole("button", { name: "문의 분석 다시 시작" })).toBeEnabled();
    expect(screen.getByTestId("vision-result")).toHaveTextContent("vision-good");
    await userEvent.click(screen.getByRole("button", { name: "문의 분석 다시 시작" }));
    await waitFor(() => expect(screen.getByTestId("text-analysis-summary")).toHaveTextContent("text-retry"));
    expect(retryCalls).toBe(1);
    expect(retryKey).toBeTruthy();
    expect(retryKey).not.toBe("text-key-old");
    expect(retryBody).toEqual({
      pipeline: "product_defect_text_extraction", pipeline_version: "2.0.0",
    });
    const stored = JSON.parse(sessionStorage.getItem("csight.workflow.v1") ?? "{}") as Record<string, unknown>;
    expect(stored).toMatchObject({
      caseId: "case-1", analysisV2RunId: "text-retry", visionRunId: "vision-good",
      idempotencyKeys: { vision: "vision-key-stable" },
    });
    expect(stored).not.toHaveProperty("retrievalRunId");
    expect(stored).not.toHaveProperty("groundingRunId");
    expect(stored).not.toHaveProperty("policyEvaluationRunId");
    expect(stored).not.toHaveProperty("idempotencyKeys.retrieval");
    expect(stored).not.toHaveProperty("idempotencyKeys.grounding");
    expect(stored).not.toHaveProperty("idempotencyKeys.policy");
    expect(screen.getByTestId("vision-result")).toHaveTextContent("vision-good");
  });

  it("resets every checkpoint ID before an in-app Case A to Case B route transition", async () => {
    const textA = run("analysis-a", "product_defect_text_extraction", "2.0.0", "2026-08-28T01:00:00Z");
    const textB = run("analysis-b", "product_defect_text_extraction", "2.0.0", "2026-08-28T02:00:00Z");
    const leakedRequests: string[] = [];
    sessionStorage.setItem("csight.workflow.v1", JSON.stringify({
      caseId: "case-a",
      analysisV2RunId: "analysis-a",
      visionRunId: "vision-a",
      retrievalRunId: "retrieval-a",
      groundingRunId: "grounding-a",
      policyEvaluationRunId: "policy-a",
      idempotencyKeys: {},
    }));

    const missingDetail = { detail: { code: "RUN_NOT_FOUND", message: "Not needed in route test" } };
    const leak = ({ request }: { request: Request }) => {
      leakedRequests.push(new URL(request.url).pathname);
      return HttpResponse.json(missingDetail, { status: 500 });
    };
    server.use(
      http.get("/api/v1/cases/case-b/analysis-runs/analysis-a", leak),
      http.get("/api/v1/cases/case-b/analysis-runs/vision-a", leak),
      http.get("/api/v1/cases/case-b/policy-retrieval-runs/retrieval-a", leak),
      http.get("/api/v1/cases/case-b/grounded-explanation-runs/grounding-a", leak),
      http.get("/api/v1/cases/case-b/policy-evaluation-runs/policy-a", leak),
      http.get("/api/v1/cases/case-b/analysis-runs", () => HttpResponse.json({
        items: [textB], page: 1, page_size: 100, total: 1,
      })),
      http.get("/api/v1/cases/case-b/analysis-runs/analysis-b", () => HttpResponse.json({
        run: textB, stages: [], extraction_result: null, extraction_result_v2: {},
        vision_results: [], failed_stages: [],
      })),
      http.get("/api/v1/cases/case-b/policy-retrieval-runs", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-b/grounded-explanation-runs", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-b/policy-evaluation-runs", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/case-a/analysis-runs/analysis-a", () => HttpResponse.json(missingDetail, { status: 404 })),
      http.get("/api/v1/cases/case-a/analysis-runs/vision-a", () => HttpResponse.json(missingDetail, { status: 404 })),
      http.get("/api/v1/cases/case-a/policy-retrieval-runs/retrieval-a", () => HttpResponse.json(missingDetail, { status: 404 })),
      http.get("/api/v1/cases/case-a/grounded-explanation-runs/grounding-a", () => HttpResponse.json(missingDetail, { status: 404 })),
      http.get("/api/v1/cases/case-a/policy-evaluation-runs/policy-a", () => HttpResponse.json(missingDetail, { status: 404 })),
      http.get("/api/v1/cases/:caseId/human-review-tasks", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/:caseId/resolution/events", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/:caseId/external-action-intents", () => HttpResponse.json({ items: [] })),
      http.get("/api/v1/cases/:caseId/resolution", () => HttpResponse.json({
        detail: { code: "CASE_RESOLUTION_NOT_FOUND", message: "No resolution" },
      }, { status: 404 })),
      http.get("/api/v1/cases/:caseId", ({ params }) => {
        const caseId = String(params.caseId);
        return HttpResponse.json({
          case_id: caseId, tenant_id: "tenant-1", domain_type: "product_defect_cs", status: "OPEN",
          order_ref: caseId === "case-a" ? "ORD-A" : "ORD-B", product_ref: `SKU-${caseId}`,
          requested_action: "UNSPECIFIED", created_at: now, updated_at: now,
          customer_message: `${caseId} 상담`, attributes: {}, created_by: "user-1",
          evidence: [], status_history: [], latest_analysis_run: caseId === "case-a" ? textA : textB,
        });
      }),
    );
    tokenVault.set("test-token", 600);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/cases/case-a"]}><Routes>
      <Route path="/cases/:caseId" element={<><Link to="/cases/case-b">B 케이스로 전환</Link><CaseWorkspacePage /></>} />
    </Routes></MemoryRouter></QueryClientProvider>);

    expect(await screen.findByRole("heading", { name: "ORD-A" })).toBeVisible();
    await userEvent.click(screen.getByRole("link", { name: "B 케이스로 전환" }));
    expect(await screen.findByRole("heading", { name: "ORD-B" })).toBeVisible();
    await waitFor(() => expect(screen.getByTestId("text-analysis-summary")).toHaveTextContent("analysis-b"));
    await waitFor(() => expect(JSON.parse(sessionStorage.getItem("csight.workflow.v1") ?? "{}")).toMatchObject({
      caseId: "case-b", analysisV2RunId: "analysis-b",
    }));
    const stored = sessionStorage.getItem("csight.workflow.v1") ?? "";
    expect(stored).not.toContain("analysis-a");
    expect(stored).not.toContain("vision-a");
    expect(stored).not.toContain("retrieval-a");
    expect(stored).not.toContain("grounding-a");
    expect(stored).not.toContain("policy-a");
    expect(leakedRequests).toEqual([]);
  });
});
