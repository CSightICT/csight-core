import { describe, expect, it, vi } from "vitest";

import type { AnalysisDetail, GroundingDetail, PolicyDetail, RetrievalDetail, ReviewTask, WorkflowSnapshot } from "../api/contracts";
import { runPolicyWorkflow, type WorkflowApi } from "./runPolicyWorkflow";

const analysis = {
  run: {
    analysis_run_id: "analysis-1", tenant_id: "tenant-1", case_id: "case-1",
    pipeline: "product_defect_text_extraction", pipeline_version: "2.0.0", trigger: "MANUAL",
    status: "SUCCEEDED", requested_by: "user-1", requested_at: "2026-08-27T00:00:00Z",
    started_at: "2026-08-27T00:00:00Z", completed_at: "2026-08-27T00:00:01Z", failure: null,
    created_at: "2026-08-27T00:00:00Z", updated_at: "2026-08-27T00:00:01Z",
  }, stages: [], extraction_result: null,
  extraction_result_v2: {}, vision_results: [], failed_stages: [],
} as AnalysisDetail;
const lifecycle = {
  case_id: "case-1", status: "SUCCEEDED", correlation_id: "correlation-1",
  created_at: "2026-08-27T00:00:00Z", started_at: "2026-08-27T00:00:00Z",
  completed_at: "2026-08-27T00:00:01Z", failure_code: null, failure_message: null,
};
const retrieval = {
  run: {
    ...lifecycle, id: "retrieval-1", analysis_run_id: "analysis-1", strategy: "RAW",
    as_of_date: "2026-08-27", top_k: 3,
  },
  query_plan: null,
  retrieval_profile: { base_mode: "HYBRID", reranker_enabled: false },
  hits: [],
} as RetrievalDetail;
const grounding = {
  run: { ...lifecycle, id: "grounding-1", retrieval_run_id: "retrieval-1", citation_pack_id: "pack-1" },
  citation_pack: { citations: [{
    citation_id: "CIT-001", rank: 1, policy_clause_id: "clause-1", document_id: "policy-1",
    document_version: "1.0.0", title: "합성 정책", section_path: ["결함"], clause_type: "ELIGIBILITY",
    text: "결함 증거와 주문 정보를 사람이 검토합니다.",
  }] },
  explanation: {}, structural_validation: {}, semantic_evaluation_status: "SKIPPED",
} as GroundingDetail;
const policy = {
  run: {
    ...lifecycle, id: "policy-1", analysis_run_id: "analysis-1", summary_status: "REVIEW_REQUIRED",
    rule_set: { name: "synthetic", version: "1.0.0", hash: "hash-1" }, as_of_date: "2026-08-27",
  },
  input_qualification: {},
  rule_results: [],
} as PolicyDetail;
const review = { id: "review-1", case_id: "case-1", policy_evaluation_run_id: "policy-1", status: "PENDING" } as ReviewTask;

function snapshot(component: Partial<WorkflowSnapshot>): WorkflowSnapshot {
  return {
    case_id: "case-1", case_status: "REVIEW_PENDING", terminal: false, degraded: false,
    retry_at: null, last_good: "CASE_RECEIVED", correlation_id: "correlation-1",
    analysis: null, stages: [], policy_retrieval: null, grounded_explanation: null,
    policy_evaluation: null, review: null, resolution: null, report: null,
    ...component,
  };
}

describe("policy workflow", () => {
  it("waits for grounding before policy and keeps RAW/top-3 fixed", async () => {
    const calls: string[] = [];
    const client: WorkflowApi = {
      startAnalysis: vi.fn(async (_case, pipeline, version) => { calls.push(`analysis:${pipeline}:${version}`); return { analysis_run_id: "analysis-1" }; }),
      getWorkflowSnapshot: vi.fn(async () => {
        calls.push("snapshot:get");
        const snapshotCount = calls.filter((item) => item === "snapshot:get").length;
        if (snapshotCount === 1) return snapshot({ analysis: { run_id: "analysis-1", status: "SUCCEEDED", started_at: null, completed_at: null, failure_code: null, correlation_id: "correlation-1" } });
        if (snapshotCount === 2) return snapshot({ policy_retrieval: { run_id: "retrieval-1", status: "SUCCEEDED", started_at: null, completed_at: null, failure_code: null, correlation_id: "correlation-1" } });
        if (snapshotCount === 3) return snapshot({ grounded_explanation: { run_id: "grounding-1", status: "SUCCEEDED", started_at: null, completed_at: null, failure_code: null, correlation_id: "correlation-1" } });
        if (snapshotCount === 4) return snapshot({ policy_evaluation: { run_id: "policy-1", status: "SUCCEEDED", started_at: null, completed_at: null, failure_code: null, correlation_id: "correlation-1" } });
        return snapshot({ review: { run_id: "review-1", status: "PENDING", started_at: null, completed_at: null, failure_code: null, correlation_id: "correlation-1" } });
      }),
      getAnalysis: vi.fn(async () => { calls.push("analysis:get"); return analysis; }),
      startRetrieval: vi.fn(async () => { calls.push("retrieval:RAW:3"); return { id: "retrieval-1" }; }),
      getRetrieval: vi.fn(async () => { calls.push("retrieval:get"); return retrieval; }),
      startGrounding: vi.fn(async () => { calls.push("grounding:start"); return { id: "grounding-1" }; }),
      getGrounding: vi.fn(async () => { calls.push("grounding:get"); return grounding; }),
      startPolicy: vi.fn(async () => { calls.push("policy:start"); return { policy_evaluation_run_id: "policy-1" }; }),
      getPolicy: vi.fn(async () => { calls.push("policy:get"); return policy; }),
      listCaseReviewTasks: vi.fn(async () => { calls.push("review:get"); return [review]; }),
    };
    const result = await runPolicyWorkflow(client, "case-1", "2026-08-27", { pollMs: 0, maxPolls: 1 });
    expect(calls).toEqual([
      "analysis:product_defect_text_extraction:2.0.0", "snapshot:get", "analysis:get",
      "retrieval:RAW:3", "snapshot:get", "retrieval:get", "grounding:start", "snapshot:get",
      "grounding:get", "policy:start", "snapshot:get", "policy:get", "snapshot:get", "review:get",
    ]);
    expect(result.reviewTask?.id).toBe("review-1");
  });

  it("stops before retrieval when Text v2 only partially succeeds", async () => {
    const client = {
      startAnalysis: vi.fn(async () => ({ analysis_run_id: "analysis-1" })),
      getWorkflowSnapshot: vi.fn(async () => snapshot({ analysis: { run_id: "analysis-1", status: "PARTIAL_SUCCESS", started_at: null, completed_at: null, failure_code: "PARTIAL", correlation_id: "correlation-1" } })),
      getAnalysis: vi.fn(async () => ({ ...analysis, run: { ...analysis.run, status: "PARTIAL_SUCCESS" } })),
      startRetrieval: vi.fn(), getRetrieval: vi.fn(), startGrounding: vi.fn(), getGrounding: vi.fn(),
      startPolicy: vi.fn(), getPolicy: vi.fn(), listCaseReviewTasks: vi.fn(),
    } as unknown as WorkflowApi;
    await expect(runPolicyWorkflow(client, "case-1", "2026-08-27", { pollMs: 0, maxPolls: 1 })).rejects.toThrow("다음 단계로 진행하지 않았습니다");
    expect(client.startRetrieval).not.toHaveBeenCalled();
  });
});
