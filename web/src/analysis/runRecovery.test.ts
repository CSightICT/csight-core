import { describe, expect, it } from "vitest";

import type {
  AnalysisRun,
  GroundingRun,
  PolicyEvaluationRun,
  PolicyRetrievalRun,
} from "../api/contracts";
import { findLatestCaseAnalysisRuns, findLatestPolicyRunSet } from "./runRecovery";

function run(overrides: Partial<AnalysisRun> & Pick<AnalysisRun, "analysis_run_id" | "pipeline" | "pipeline_version" | "requested_at">): AnalysisRun {
  return {
    tenant_id: "tenant-1",
    case_id: "case-1",
    trigger: "USER_REQUEST",
    status: "SUCCEEDED",
    requested_by: "user-1",
    started_at: overrides.requested_at,
    completed_at: overrides.requested_at,
    failure: null,
    created_at: overrides.requested_at,
    updated_at: overrides.requested_at,
    ...overrides,
  };
}

describe("latest Case analysis recovery", () => {
  it("selects the latest Text v2 and latest Vision run independently of list order", () => {
    const recovered = findLatestCaseAnalysisRuns([
      run({ analysis_run_id: "vision-old", pipeline: "product_defect_multimodal_analysis", pipeline_version: "1.0.0", requested_at: "2026-08-27T01:00:00Z" }),
      run({ analysis_run_id: "text-new", pipeline: "product_defect_text_extraction", pipeline_version: "2.0.0", requested_at: "2026-08-27T04:00:00Z" }),
      run({ analysis_run_id: "vision-new", pipeline: "product_defect_multimodal_analysis", pipeline_version: "1.0.0", requested_at: "2026-08-27T03:00:00Z" }),
      run({ analysis_run_id: "text-old", pipeline: "product_defect_text_extraction", pipeline_version: "2.0.0", requested_at: "2026-08-27T02:00:00Z" }),
    ]);

    expect(recovered).toEqual({ textV2RunId: "text-new", visionRunId: "vision-new" });
  });

  it("does not recover Text v1 as the Text v2 workflow checkpoint", () => {
    const recovered = findLatestCaseAnalysisRuns([
      run({ analysis_run_id: "text-v1", pipeline: "product_defect_text_extraction", pipeline_version: "1.0.0", requested_at: "2026-08-27T05:00:00Z" }),
    ]);

    expect(recovered).toEqual({ textV2RunId: null, visionRunId: null });
  });

  it("uses a stable run-id tie break when timestamps are identical", () => {
    const recovered = findLatestCaseAnalysisRuns([
      run({ analysis_run_id: "vision-a", pipeline: "product_defect_multimodal_analysis", pipeline_version: "1.0.0", requested_at: "2026-08-27T03:00:00Z" }),
      run({ analysis_run_id: "vision-b", pipeline: "product_defect_multimodal_analysis", pipeline_version: "1.0.0", requested_at: "2026-08-27T03:00:00Z" }),
    ]);

    expect(recovered.visionRunId).toBe("vision-b");
  });

  it("skips newer failed analysis runs while preserving older usable results", () => {
    const recovered = findLatestCaseAnalysisRuns([
      run({ analysis_run_id: "text-good", pipeline: "product_defect_text_extraction", pipeline_version: "2.0.0", requested_at: "2026-08-27T01:00:00Z" }),
      run({ analysis_run_id: "text-failed", pipeline: "product_defect_text_extraction", pipeline_version: "2.0.0", requested_at: "2026-08-27T04:00:00Z", status: "FAILED" }),
      run({ analysis_run_id: "vision-partial", pipeline: "product_defect_multimodal_analysis", pipeline_version: "1.0.0", requested_at: "2026-08-27T02:00:00Z", status: "PARTIAL_SUCCESS" }),
      run({ analysis_run_id: "vision-failed", pipeline: "product_defect_multimodal_analysis", pipeline_version: "1.0.0", requested_at: "2026-08-27T05:00:00Z", status: "FAILED" }),
    ]);

    expect(recovered).toEqual({ textV2RunId: "text-good", visionRunId: "vision-partial" });
  });

  it("returns no checkpoint candidate when only failed analysis runs exist", () => {
    const recovered = findLatestCaseAnalysisRuns([
      run({ analysis_run_id: "text-failed", pipeline: "product_defect_text_extraction", pipeline_version: "2.0.0", requested_at: "2026-08-27T04:00:00Z", status: "FAILED" }),
      run({ analysis_run_id: "vision-failed", pipeline: "product_defect_multimodal_analysis", pipeline_version: "1.0.0", requested_at: "2026-08-27T05:00:00Z", status: "FAILED" }),
    ]);

    expect(recovered).toEqual({ textV2RunId: null, visionRunId: null });
  });
});

function lifecycle(createdAt: string) {
  return {
    case_id: "case-1",
    status: "SUCCEEDED",
    correlation_id: "correlation-1",
    created_at: createdAt,
    started_at: createdAt,
    completed_at: createdAt,
    failure_code: null,
    failure_message: null,
  };
}

function retrieval(
  id: string,
  analysisRunId: string,
  createdAt: string,
  status = "SUCCEEDED",
): PolicyRetrievalRun {
  return {
    ...lifecycle(createdAt),
    id,
    analysis_run_id: analysisRunId,
    strategy: "RAW",
    as_of_date: "2026-08-28",
    top_k: 3,
    status,
  };
}

function grounding(
  id: string,
  retrievalRunId: string,
  createdAt: string,
  status = "SUCCEEDED",
): GroundingRun {
  return {
    ...lifecycle(createdAt),
    id,
    retrieval_run_id: retrievalRunId,
    citation_pack_id: `pack-${id}`,
    status,
  };
}

function policy(
  id: string,
  analysisRunId: string,
  createdAt: string,
  status = "SUCCEEDED",
): PolicyEvaluationRun {
  return {
    ...lifecycle(createdAt),
    id,
    analysis_run_id: analysisRunId,
    summary_status: "REVIEW_REQUIRED",
    rule_set: { name: "synthetic", version: "1.0.0", hash: "hash-1" },
    as_of_date: "2026-08-28",
    status,
  };
}

describe("latest policy run-set recovery", () => {
  it("recovers linked retrieval-grounding plus the independently anchored policy run", () => {
    const recovered = findLatestPolicyRunSet(
      "text-latest",
      [
        retrieval("retrieval-other", "text-other", "2026-08-28T06:00:00Z"),
        retrieval("retrieval-complete", "text-latest", "2026-08-28T04:00:00Z"),
        retrieval("retrieval-new-incomplete", "text-latest", "2026-08-28T05:00:00Z"),
      ],
      [
        grounding("grounding-other", "retrieval-other", "2026-08-28T06:01:00Z"),
        grounding("grounding-complete", "retrieval-complete", "2026-08-28T04:01:00Z"),
      ],
      [
        policy("policy-other", "text-other", "2026-08-28T06:02:00Z"),
        policy("policy-old", "text-latest", "2026-08-28T04:02:00Z"),
        policy("policy-latest", "text-latest", "2026-08-28T05:02:00Z"),
      ],
    );

    expect(recovered).toEqual({
      retrievalRunId: "retrieval-complete",
      groundingRunId: "grounding-complete",
      policyEvaluationRunId: "policy-latest",
    });
  });

  it("excludes failed runs and will not cross retrieval or analysis links", () => {
    const recovered = findLatestPolicyRunSet(
      "text-latest",
      [retrieval("retrieval-good", "text-latest", "2026-08-28T01:00:00Z")],
      [
        grounding("grounding-crossed", "retrieval-other", "2026-08-28T03:00:00Z"),
        grounding("grounding-failed", "retrieval-good", "2026-08-28T04:00:00Z", "FAILED"),
      ],
      [policy("policy-failed", "text-latest", "2026-08-28T05:00:00Z", "FAILED")],
    );

    expect(recovered).toEqual({
      retrievalRunId: "retrieval-good",
      groundingRunId: null,
      policyEvaluationRunId: null,
    });
  });

  it("recovers queued and running linked IDs so a cold session cannot duplicate active stages", () => {
    const recovered = findLatestPolicyRunSet(
      "text-latest",
      [
        retrieval("retrieval-complete", "text-latest", "2026-08-28T01:00:00Z"),
        retrieval("retrieval-active", "text-latest", "2026-08-28T02:00:00Z", "QUEUED"),
      ],
      [
        grounding("grounding-complete", "retrieval-complete", "2026-08-28T01:01:00Z"),
        grounding("grounding-active", "retrieval-active", "2026-08-28T02:01:00Z", "RUNNING"),
        grounding("grounding-crossed", "retrieval-other", "2026-08-28T04:00:00Z", "RUNNING"),
      ],
      [
        policy("policy-complete", "text-latest", "2026-08-28T01:02:00Z"),
        policy("policy-active", "text-latest", "2026-08-28T02:02:00Z", "RUNNING"),
        policy("policy-other", "text-other", "2026-08-28T05:00:00Z", "RUNNING"),
      ],
    );

    expect(recovered).toEqual({
      retrievalRunId: "retrieval-active",
      groundingRunId: "grounding-active",
      policyEvaluationRunId: "policy-active",
    });
  });

  it("respects a valid partial checkpoint instead of mixing it with another retrieval", () => {
    const recovered = findLatestPolicyRunSet(
      "text-latest",
      [
        retrieval("retrieval-old", "text-latest", "2026-08-28T01:00:00Z"),
        retrieval("retrieval-new", "text-latest", "2026-08-28T02:00:00Z"),
      ],
      [
        grounding("grounding-old", "retrieval-old", "2026-08-28T01:01:00Z"),
        grounding("grounding-new", "retrieval-new", "2026-08-28T02:01:00Z"),
      ],
      [policy("policy-latest", "text-latest", "2026-08-28T03:00:00Z")],
      { retrievalRunId: "retrieval-old" },
    );

    expect(recovered).toEqual({
      retrievalRunId: "retrieval-old",
      groundingRunId: "grounding-old",
      policyEvaluationRunId: "policy-latest",
    });
  });
});
