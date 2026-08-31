import { z } from "zod";

import type {
  AnalysisDetail,
  AnalysisRun,
  AuthCapabilities,
  CaseDetail,
  CasePage,
  CustomerCommunicationSimulation,
  CurrentUser,
  DataAssetSummary,
  EvidenceAccessUrl,
  ExternalActionIntent,
  ExternalActionIntentDetail,
  GroundingRun,
  GroundingDetail,
  OperatorCasePage,
  OperatorReviewPage,
  OperationsFailures,
  OperationsOverview,
  OnboardingReadiness,
  OidcSessionResponse,
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
  WorkflowSnapshot,
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

const oidcSessionSchema = z.object({
  authenticated: z.literal(true),
  csrf_token: z.string().min(32),
  principal: userSchema,
  expiry: z.object({
    idle_expires_at: z.string(), absolute_expires_at: z.string(), effective_expires_at: z.string(),
    expiry_warning_at: z.string(), expires_in_seconds: z.number().int().nonnegative(),
    expires_within_five_minutes: z.boolean(),
  }),
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

const optionalQueueText = z.unknown().optional().transform((value) => typeof value === "string" ? value : null);
const queueCount = z.number().int().nonnegative().catch(0);
const queueCountsSchema = z.object({
  all: queueCount,
  my: queueCount,
  unassigned: queueCount,
  urgent: queueCount,
  waiting_evidence: queueCount,
  complete: queueCount,
});
const operatorCaseItemSchema = z.object({
  case_id: z.string().min(1),
  case_status: z.string().min(1),
  order_ref: z.string(),
  product_ref: z.string(),
  requested_action: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  review_task_id: optionalQueueText,
  review_status: optionalQueueText,
  review_priority: optionalQueueText,
  assignee_id: optionalQueueText,
  assignment_version: z.number().int().nonnegative(),
  resolution_status: optionalQueueText,
  report_id: optionalQueueText,
  report_generated_at: optionalQueueText,
});
const operatorReviewItemSchema = z.object({
  review_task_id: z.string().min(1),
  case_id: z.string().min(1),
  case_status: z.string().min(1),
  order_ref: z.string(),
  product_ref: z.string(),
  requested_action: z.string(),
  task_type: z.string(),
  priority: z.string(),
  status: z.string().min(1),
  assignee_id: optionalQueueText,
  version: z.number().int().positive(),
  created_at: z.string(),
  updated_at: z.string(),
  resolution_status: optionalQueueText,
  report_id: optionalQueueText,
  report_generated_at: optionalQueueText,
});

const workflowComponentSchema = z.object({
  run_id: z.string().min(1),
  status: z.string().min(1),
  started_at: stringOrNull,
  completed_at: stringOrNull,
  failure_code: stringOrNull,
  correlation_id: stringOrNull,
});
const workflowStageSchema = z.object({
  stage_type: z.string().min(1),
  status: z.string().min(1),
  attempt_count: z.number().int().nonnegative(),
  next_attempt_at: stringOrNull,
  failure_code: stringOrNull,
});
const workflowSnapshotSchema = z.object({
  case_id: z.string().min(1),
  case_status: z.string().min(1),
  terminal: z.boolean(),
  degraded: z.boolean(),
  retry_at: stringOrNull,
  last_good: z.string().min(1),
  correlation_id: stringOrNull,
  analysis: workflowComponentSchema.nullable(),
  stages: z.array(workflowStageSchema),
  policy_retrieval: workflowComponentSchema.nullable(),
  grounded_explanation: workflowComponentSchema.nullable(),
  policy_evaluation: workflowComponentSchema.nullable(),
  review: workflowComponentSchema.nullable(),
  resolution: workflowComponentSchema.nullable(),
  report: workflowComponentSchema.nullable(),
});
const nonnegativeInteger = z.number().int().nonnegative();
const operationsQueueSchema = z.object({
  queue: z.string(), backlog_count: nonnegativeInteger, pending_count: nonnegativeInteger,
  processing_count: nonnegativeInteger, published_unconsumed_count: nonnegativeInteger,
  failed_count: nonnegativeInteger, retry_count: nonnegativeInteger, stalled_count: nonnegativeInteger,
  oldest_backlog_age_seconds: nonnegativeInteger.nullable(), last_healthy_at: stringOrNull,
});
const operationsProcessingSchema = z.object({
  component: z.string(), backlog_count: nonnegativeInteger, running_count: nonnegativeInteger,
  retry_count: nonnegativeInteger, partial_success_count: nonnegativeInteger,
  failed_count: nonnegativeInteger, stalled_count: nonnegativeInteger,
  oldest_backlog_age_seconds: nonnegativeInteger.nullable(), last_healthy_at: stringOrNull,
});
const operationsVersionSchema = z.object({
  kind: z.string(), component: z.string(), name: z.string(), version: z.string(),
  revision: stringOrNull, numeric_value: z.number().nullable(), source: z.string(), observed_at: z.string(),
});
const operationsFailureSchema = z.object({
  component: z.string(), failed_count: nonnegativeInteger, partial_success_count: nonnegativeInteger,
  retry_count: nonnegativeInteger, stalled_count: nonnegativeInteger, oldest_signal_at: stringOrNull,
  latest_signal_at: stringOrNull, last_healthy_at: stringOrNull,
  top_failure_codes: z.array(z.object({ code: z.string(), count: z.number().int().positive() })).max(3),
});

export const decodeToken = (value: unknown): TokenResponse => tokenSchema.parse(value);
export const decodeCurrentUser = (value: unknown): CurrentUser => userSchema.parse(value);
export const decodeOidcSession = (value: unknown): OidcSessionResponse =>
  oidcSessionSchema.parse(value) as OidcSessionResponse;
export const decodeAuthCapabilities = (value: unknown): AuthCapabilities => z.object({
  oidc_enabled: z.boolean(), legacy_password_enabled: z.boolean(),
}).parse(value) as AuthCapabilities;

export const decodeCasePage = (value: unknown): CasePage => z.object({
  items: z.array(caseSummarySchema), page: z.number(), page_size: z.number(), total: z.number(),
}).parse(value) as CasePage;

export const decodeOperatorCasePage = (value: unknown): OperatorCasePage => z.object({
  items: z.array(operatorCaseItemSchema),
  counts: queueCountsSchema,
  next_cursor: optionalQueueText,
}).parse(value) as OperatorCasePage;

export const decodeCaseAssignment = (value: unknown) => z.object({
  case_id: z.string().min(1),
  current_assignee_id: optionalQueueText,
  version: nonnegativeInteger,
  assigned_by: optionalQueueText,
  assignment_type: z.enum(["ADMIN_ASSIGNMENT", "ADMIN_REASSIGNMENT", "REVIEW_TASK_BACKFILL"]).nullable(),
  rationale: optionalQueueText,
  assigned_at: optionalQueueText,
}).parse(value);

export const decodeOperatorReviewPage = (value: unknown): OperatorReviewPage => z.object({
  items: z.array(operatorReviewItemSchema),
  counts: queueCountsSchema,
  next_cursor: optionalQueueText,
}).parse(value) as OperatorReviewPage;

export const decodeWorkflowSnapshot = (value: unknown): WorkflowSnapshot =>
  workflowSnapshotSchema.parse(value) as WorkflowSnapshot;

export const decodeOperationsOverview = (value: unknown): OperationsOverview => z.object({
  generated_at: z.string(), stalled_after_seconds: z.number().int().positive(),
  total_backlog_count: nonnegativeInteger, total_stalled_count: nonnegativeInteger,
  queues: z.array(operationsQueueSchema), processing: z.array(operationsProcessingSchema),
  active_versions: z.array(operationsVersionSchema).max(64),
}).parse(value) as OperationsOverview;

export const decodeOperationsFailures = (value: unknown): OperationsFailures => z.object({
  generated_at: z.string(), lookback_seconds: z.number().int().positive(),
  total_failed_count: nonnegativeInteger, total_partial_success_count: nonnegativeInteger,
  total_retry_count: nonnegativeInteger, total_stalled_count: nonnegativeInteger,
  components: z.array(operationsFailureSchema),
}).parse(value) as OperationsFailures;

export const decodeOnboardingReadiness = (value: unknown): OnboardingReadiness => z.object({
  pilot_ready: z.boolean(),
  gates: z.array(z.object({
    code: z.string().min(1),
    status: z.enum(["PASS", "FAIL"]),
    description: z.string().min(1),
  })).length(6),
}).parse(value) as OnboardingReadiness;

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

export const decodeReviewAssignees = (value: unknown) => z.object({
  items: z.array(z.object({
    user_id: z.string(), display_name: z.string(), email: z.string(), roles: z.array(z.string()),
  })),
}).parse(value).items;

export const decodeReviewTaskDetail = (value: unknown): ReviewTaskDetail => z.object({
  task: reviewTaskSchema, packet: record, actions: z.array(record), decision: record.nullable(),
  rule_results: z.array(record), citation_items: z.array(record), grounded_explanation: record.nullable(),
  inquiry_summary: z.string().nullable(), policy_similarity: z.array(record),
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
  schema_version: z.string(), generated_at: z.string(), eligible_source_scope: z.literal("PILOT_LIVE"),
  eligible_case_count: z.number().int().nonnegative(), excluded_case_count: z.number().int().nonnegative(), review_time: metricSchema,
  recommendation_difference_rate: metricSchema, additional_evidence_request_rate: metricSchema,
  action_input_missing_rate: metricSchema, dry_run_success_rate: metricSchema,
  analysis_failure_rate: metricSchema, analysis_partial_success_rate: metricSchema,
}).parse(value) as PocSummary;

const customerCommunicationSchema = z.object({
  schema_version: z.string(), communication_id: z.string(), case_id: z.string(), review_report_id: z.string(),
  channel: z.string(), template_name: z.string(), template_version: z.string(), recipient_label: z.string(),
  subject: z.string(), body: z.string(), delivery_status: z.string(), side_effects_performed: z.boolean(),
  created_at: z.string(), content_hash: z.string(),
});
export const decodeCustomerCommunication = (value: unknown): CustomerCommunicationSimulation =>
  customerCommunicationSchema.parse(value) as CustomerCommunicationSimulation;
export const decodeCustomerCommunications = (value: unknown): CustomerCommunicationSimulation[] =>
  z.array(customerCommunicationSchema).parse(value) as CustomerCommunicationSimulation[];

const learningAssetSchema = z.object({
  schema_version: z.string(), asset_id: z.string(), case_id: z.string(), review_report_id: z.string(),
  feature_snapshot: record, label_snapshot: record, version_snapshot: record, privacy_scope: record,
  created_at: z.string(), content_hash: z.string(),
});
export const decodeDataAssetSummary = (value: unknown): DataAssetSummary => z.object({
  schema_version: z.string(), generated_at: z.string(), total_records: z.number().int().nonnegative(),
  eligible_records: z.number().int().nonnegative(), excluded_records: z.number().int().nonnegative(),
  eligible_source_scope: z.literal("PILOT_LIVE"), source_scope_distribution: z.record(z.string(), z.number().int().nonnegative()),
  baseline_minimum: z.number().int().positive(), drift_review_minimum: z.number().int().positive(),
  readiness_status: z.string(), drift_evaluation_available: z.boolean(),
  decision_distribution: z.record(z.string(), z.number().int().nonnegative()),
  resolution_distribution: z.record(z.string(), z.number().int().nonnegative()),
  product_distribution: z.record(z.string(), z.number().int().nonnegative()),
  model_version_distribution: z.record(z.string(), z.number().int().nonnegative()),
  policy_version_distribution: z.record(z.string(), z.number().int().nonnegative()),
  recent_records: z.array(learningAssetSchema),
}).parse(value) as DataAssetSummary;
