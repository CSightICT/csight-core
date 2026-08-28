import { z } from "zod";

import type {
  AnalysisDetail,
  AnalysisRun,
  CaseDetail,
  CasePage,
  CurrentUser,
  EvidenceAccessUrl,
  ExternalActionIntent,
  ExternalActionIntentDetail,
  GroundingRun,
  GroundingDetail,
  PolicyEvaluationRun,
  PocSummary,
  PolicyDetail,
  PolicyRetrievalRun,
  ResolutionView,
  RetrievalDetail,
  ReviewActionResult,
  ReviewReport,
  ReviewTask,
  ReviewTaskDetail,
  TokenResponse,
} from "./contracts";

const record = z.record(z.string(), z.unknown());
const stringOrNull = z.string().nullable();

const tokenSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.literal("bearer"),
  expires_in: z.number().int().positive(),
});

const userSchema = z.object({
  user_id: z.string(), tenant_id: z.string(), email: z.string(), display_name: z.string(),
  roles: z.array(z.string()),
});

const evidenceSchema = z.object({
  evidence_id: z.string(), tenant_id: z.string(), case_id: z.string(), evidence_type: z.string(),
  upload_status: z.string(), original_filename: z.string(), content_type: z.string(),
  size_bytes: z.number(), sha256: z.string(), width: z.number(), height: z.number(),
  created_by: z.string(), created_at: z.string(), updated_at: z.string(),
});

const evidenceAccessUrlSchema = z.object({
  evidence_id: z.string().min(1),
  url: z.string().min(1).refine((value) => {
    try {
      const parsed = new URL(value);
      return (parsed.protocol === "http:" || parsed.protocol === "https:")
        && parsed.username === ""
        && parsed.password === "";
    } catch {
      return false;
    }
  }, "Evidence URL must use HTTP or HTTPS without embedded credentials."),
  expires_at: z.string().min(1),
});

const runSchema = z.object({
  analysis_run_id: z.string(), tenant_id: z.string(), case_id: z.string(), pipeline: z.string(),
  pipeline_version: z.string(), trigger: z.string(), status: z.string(), requested_by: z.string(),
  requested_at: z.string(), started_at: stringOrNull, completed_at: stringOrNull,
  failure: z.object({ code: z.string(), retryable: z.boolean() }).nullable(),
  created_at: z.string(), updated_at: z.string(),
});

const caseSummarySchema = z.object({
  case_id: z.string(), tenant_id: z.string(), domain_type: z.string(), status: z.string(),
  order_ref: z.string(), product_ref: z.string(), requested_action: z.string(),
  created_at: z.string(), updated_at: z.string(),
});

const reviewTaskSchema = z.object({
  id: z.string(), case_id: z.string(), policy_evaluation_run_id: z.string(), task_type: z.string(),
  priority: z.string(), status: z.string(), current_assignee_id: z.string().nullable(),
  version: z.number().int().positive(), mapping_rule_name: z.string(), mapping_rule_version: z.string(),
  created_at: z.string(), updated_at: z.string(), resolved_at: z.string().nullable(),
});

export const decodeToken = (value: unknown): TokenResponse => tokenSchema.parse(value);
export const decodeCurrentUser = (value: unknown): CurrentUser => userSchema.parse(value);

export const decodeCasePage = (value: unknown): CasePage => z.object({
  items: z.array(caseSummarySchema), page: z.number(), page_size: z.number(), total: z.number(),
}).parse(value) as CasePage;

export const decodeCaseDetail = (value: unknown): CaseDetail => caseSummarySchema.extend({
  customer_message: z.string(), attributes: record, created_by: z.string(), evidence: z.array(evidenceSchema),
  status_history: z.array(z.object({
    history_id: z.string(), from_status: z.string().nullable(), to_status: z.string(),
    actor_id: z.string(), reason: z.string(), occurred_at: z.string(),
  })),
  latest_analysis_run: runSchema.nullable(),
}).parse(value) as CaseDetail;

export const decodeEvidenceAccessUrl = (value: unknown): EvidenceAccessUrl =>
  evidenceAccessUrlSchema.parse(value) as EvidenceAccessUrl;

export const decodeAnalysisRun = (value: unknown): AnalysisRun => runSchema.parse(value) as AnalysisRun;

export const decodeAnalysisDetail = (value: unknown): AnalysisDetail => z.object({
  run: runSchema,
  stages: z.array(record.and(z.object({
    stage_run_id: z.string(), stage_type: z.string(), status: z.string(), model_name: z.string(),
    model_version: z.string(), prompt_version: z.string(), attempt_count: z.number(),
  }))),
  extraction_result: record.nullable(),
  extraction_result_v2: record.nullable(),
  vision_results: z.array(record),
  failed_stages: z.array(z.string()),
}).parse(value) as AnalysisDetail;

const lifecycleRunSchema = z.object({
  id: z.string(), case_id: z.string(), status: z.string(), correlation_id: z.string(), created_at: z.string(),
  started_at: stringOrNull, completed_at: stringOrNull, failure_code: stringOrNull, failure_message: stringOrNull,
});
const policyRetrievalRunSchema = lifecycleRunSchema.extend({
  analysis_run_id: z.string(), strategy: z.string(), as_of_date: z.string(), top_k: z.number().int().positive(),
});
const groundingRunSchema = lifecycleRunSchema.extend({
  retrieval_run_id: z.string(), citation_pack_id: z.string(),
});
const policyEvaluationRunSchema = lifecycleRunSchema.extend({
  analysis_run_id: z.string(), summary_status: stringOrNull, rule_set: z.record(z.string(), z.string()), as_of_date: z.string(),
});

const policyCitationSchema = z.object({
  citation_id: z.string().min(1), rank: z.number().int().positive(), policy_clause_id: z.string().min(1),
  document_id: z.string().min(1), document_version: z.string().min(1), title: z.string().min(1),
  section_path: z.array(z.string().min(1)).min(1), clause_type: z.string().min(1), text: z.string().min(1),
});

const policyCitationPackSchema = record.and(z.object({ citations: z.array(policyCitationSchema) }));

export const decodeRetrievalDetail = (value: unknown): RetrievalDetail => z.object({
  run: record.and(policyRetrievalRunSchema),
  query_plan: record.nullable(), retrieval_profile: record, hits: z.array(record),
}).parse(value) as RetrievalDetail;

export const decodePolicyRetrievalRuns = (value: unknown): PolicyRetrievalRun[] =>
  z.object({ items: z.array(policyRetrievalRunSchema) }).parse(value).items as PolicyRetrievalRun[];

export const decodeGroundingDetail = (value: unknown): GroundingDetail => z.object({
  run: record.and(groundingRunSchema),
  citation_pack: policyCitationPackSchema, explanation: record.nullable(), structural_validation: record.nullable(),
  semantic_evaluation_status: z.string(),
}).parse(value) as GroundingDetail;

export const decodeGroundingRuns = (value: unknown): GroundingRun[] =>
  z.object({ items: z.array(groundingRunSchema) }).parse(value).items as GroundingRun[];

export const decodePolicyDetail = (value: unknown): PolicyDetail => z.object({
  run: record.and(policyEvaluationRunSchema),
  input_qualification: z.record(z.string(), z.string()), rule_results: z.array(record),
}).parse(value) as PolicyDetail;

export const decodePolicyEvaluationRuns = (value: unknown): PolicyEvaluationRun[] =>
  z.object({ items: z.array(policyEvaluationRunSchema) }).parse(value).items as PolicyEvaluationRun[];

export const decodeReviewTasks = (value: unknown): ReviewTask[] =>
  z.object({ items: z.array(reviewTaskSchema) }).parse(value).items as ReviewTask[];

export const decodeReviewTaskDetail = (value: unknown): ReviewTaskDetail => z.object({
  task: reviewTaskSchema, packet: record, actions: z.array(record), decision: record.nullable(),
  rule_results: z.array(record), citation_items: z.array(record), grounded_explanation: record.nullable(),
}).parse(value) as ReviewTaskDetail;

export const decodeReviewActionResult = (value: unknown): ReviewActionResult => z.object({
  task: reviewTaskSchema, decision: record.nullable().optional().transform((item) => item ?? null),
}).parse(value) as ReviewActionResult;

const resolutionSchema = z.object({
  id: z.string(), case_id: z.string(), source_review_task_id: z.string(), source_human_decision_id: z.string(),
  status: z.string(), version: z.number().int().positive(), mapping_name: z.string(), mapping_version: z.string(),
  resolution_schema_version: z.string(), missing_fields: z.array(z.string()), invalid_fields: z.array(z.string()),
  failure_code: z.string().nullable(), failure_message: z.string().nullable(), correlation_id: z.string(),
  created_at: z.string(), updated_at: z.string(),
});
const intentSchema = z.object({
  id: z.string(), case_id: z.string(), resolution_id: z.string(), human_decision_id: z.string(),
  action_type: z.string(), mode: z.string(), order_ref: z.string(), product_ref: z.string().nullable().optional(),
  amount: z.string().nullable().optional(), currency: z.string().nullable().optional(), quantity: z.number().int().nullable().optional(),
  shipping_address_ref: z.string().nullable().optional(), mapping_name: z.string(), mapping_version: z.string(),
  intent_schema_version: z.string(), content_hash: z.string(), created_at: z.string(),
});
const attemptSchema = z.object({
  id: z.string(), case_id: z.string(), resolution_id: z.string(), external_action_intent_id: z.string(),
  attempt_number: z.number().int().positive(), status: z.string(), mode: z.string(), started_at: z.string(),
  completed_at: z.string().nullable(), failure_code: z.string().nullable(), failure_message: z.string().nullable(),
});
const simulationResultSchema = z.object({
  id: z.string(), case_id: z.string(), resolution_id: z.string(), external_action_intent_id: z.string(),
  simulation_attempt_id: z.string(), outcome: z.string(), mode: z.string(), side_effects_performed: z.boolean(),
  failure_code: z.string().nullable(), failure_message: z.string().nullable(), simulated_request: record,
  simulated_response: record, result_schema_version: z.string(), content_hash: z.string(), created_at: z.string(),
});

export const decodeResolution = (value: unknown): ResolutionView => resolutionSchema.parse(value) as ResolutionView;
export const decodeIntentList = (value: unknown): ExternalActionIntent[] => {
  const parsed = z.union([z.array(intentSchema), z.object({ items: z.array(intentSchema) })]).parse(value);
  return (Array.isArray(parsed) ? parsed : parsed.items) as ExternalActionIntent[];
};
export const decodeIntentDetail = (value: unknown): ExternalActionIntentDetail => z.object({
  intent: intentSchema,
  attempts: z.array(attemptSchema),
  results: z.array(simulationResultSchema),
}).parse(value) as ExternalActionIntentDetail;
export const decodeReviewReport = (value: unknown): ReviewReport => z.object({
  schema_version: z.string(), report_id: z.string(), case_id: z.string(), resolution_id: z.string(),
  resolution_version: z.number().int().positive(), terminal_event_id: z.string(), case_snapshot: record,
  analysis_snapshot: record, policy_snapshot: record, review_snapshot: record, resolution_snapshot: record,
  dry_run_snapshot: record, qualification_snapshot: record, data_scope: record, generated_at: z.string(), content_hash: z.string(),
}).parse(value) as ReviewReport;
const metricSchema = z.object({
  numerator: z.number().nonnegative(), denominator: z.number().int().nonnegative(), sample_count: z.number().int().nonnegative(),
  value: z.number().nullable(), unit: z.string(),
});
export const decodePocSummary = (value: unknown): PocSummary => z.object({
  schema_version: z.string(), generated_at: z.string(), review_time: metricSchema,
  recommendation_difference_rate: metricSchema, additional_evidence_request_rate: metricSchema,
  action_input_missing_rate: metricSchema, dry_run_success_rate: metricSchema,
  analysis_failure_rate: metricSchema, analysis_partial_success_rate: metricSchema,
}).parse(value) as PocSummary;
