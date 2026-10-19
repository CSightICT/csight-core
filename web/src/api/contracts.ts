export type Role = "ADMIN" | "REVIEWER" | "OPERATOR" | string;

export interface CurrentUser {
  user_id: string;
  tenant_id: string;
  email: string;
  display_name: string;
  roles: Role[];
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface OidcSessionResponse {
  authenticated: true;
  csrf_token: string;
  principal: CurrentUser;
  expiry: {
    idle_expires_at: string;
    absolute_expires_at: string;
    effective_expires_at: string;
    expiry_warning_at: string;
    expires_in_seconds: number;
    expires_within_five_minutes: boolean;
  };
}

export interface AuthCapabilities {
  oidc_enabled: boolean;
  legacy_password_enabled: boolean;
}

export type CaseStatus =
  | "OPEN"
  | "EVIDENCE_PENDING"
  | "ANALYSIS_PENDING"
  | "ANALYSIS_IN_PROGRESS"
  | "REVIEW_PENDING"
  | "RESOLVED"
  | string;

export type RequestedAction =
  | "UNSPECIFIED"
  | "REFUND"
  | "EXCHANGE"
  | "RESHIPMENT"
  | "REPAIR"
  | "PROVIDE_INFORMATION"
  | string;

export interface CaseSummary {
  case_id: string;
  tenant_id: string;
  domain_type: string;
  status: CaseStatus;
  order_ref: string;
  product_ref: string;
  requested_action: RequestedAction;
  created_at: string;
  updated_at: string;
}

export interface Evidence {
  evidence_id: string;
  tenant_id: string;
  case_id: string;
  evidence_type: string;
  upload_status: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  width: number;
  height: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface EvidenceAccessUrl {
  evidence_id: string;
  url: string;
  expires_at: string;
}

export interface CaseDetail extends CaseSummary {
  customer_message: string;
  attributes: Record<string, unknown>;
  created_by: string;
  evidence: Evidence[];
  status_history: Array<{
    history_id: string;
    from_status: string | null;
    to_status: string;
    actor_id: string;
    reason: string;
    occurred_at: string;
  }>;
  latest_analysis_run: AnalysisRun | null;
}

export interface CasePage {
  items: CaseSummary[];
  page: number;
  page_size: number;
  total: number;
}

export type OperatorQueueView = "all" | "my" | "unassigned" | "urgent" | "waiting_evidence" | "complete";
export type OperatorQueueSort = "newest" | "oldest";

export interface OperatorQueueCounts {
  all: number;
  my: number;
  unassigned: number;
  urgent: number;
  waiting_evidence: number;
  complete: number;
}

export interface OperatorCaseItem {
  case_id: string;
  case_status: string;
  order_ref: string;
  product_ref: string;
  requested_action: string;
  inquiry_preview?: string | null;
  created_at: string;
  updated_at: string;
  review_task_id: string | null;
  review_status: string | null;
  review_priority: string | null;
  assignee_id: string | null;
  assignment_version: number;
  resolution_status: string | null;
  report_id: string | null;
  report_generated_at: string | null;
}

export interface OperatorReviewItem {
  review_task_id: string;
  case_id: string;
  case_status: string;
  order_ref: string;
  product_ref: string;
  requested_action: string;
  inquiry_preview?: string | null;
  task_type: string;
  priority: string;
  status: string;
  assignee_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  resolution_status: string | null;
  report_id: string | null;
  report_generated_at: string | null;
}

export interface OperatorCasePage {
  items: OperatorCaseItem[];
  counts: OperatorQueueCounts;
  next_cursor: string | null;
}

export interface CaseAssignment {
  case_id: string;
  current_assignee_id: string | null;
  version: number;
  assigned_by: string | null;
  assignment_type: "ADMIN_ASSIGNMENT" | "ADMIN_REASSIGNMENT" | "REVIEW_TASK_BACKFILL" | null;
  rationale: string | null;
  assigned_at: string | null;
}

export interface OperatorReviewPage {
  items: OperatorReviewItem[];
  counts: OperatorQueueCounts;
  next_cursor: string | null;
}

export interface WorkflowComponentSnapshot {
  run_id: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  failure_code: string | null;
  correlation_id: string | null;
}

export interface WorkflowStageSnapshot {
  stage_type: string;
  status: string;
  attempt_count: number;
  next_attempt_at: string | null;
  failure_code: string | null;
}

export interface WorkflowSnapshot {
  case_id: string;
  case_status: string;
  terminal: boolean;
  degraded: boolean;
  retry_at: string | null;
  last_good: string;
  correlation_id: string | null;
  analysis: WorkflowComponentSnapshot | null;
  stages: WorkflowStageSnapshot[];
  policy_retrieval: WorkflowComponentSnapshot | null;
  grounded_explanation: WorkflowComponentSnapshot | null;
  policy_evaluation: WorkflowComponentSnapshot | null;
  review: WorkflowComponentSnapshot | null;
  resolution: WorkflowComponentSnapshot | null;
  report: WorkflowComponentSnapshot | null;
}

export interface OperationsQueueSnapshot {
  queue: string;
  backlog_count: number;
  pending_count: number;
  processing_count: number;
  published_unconsumed_count: number;
  failed_count: number;
  retry_count: number;
  stalled_count: number;
  oldest_backlog_age_seconds: number | null;
  last_healthy_at: string | null;
}

export interface OperationsProcessingSnapshot {
  component: string;
  backlog_count: number;
  running_count: number;
  retry_count: number;
  partial_success_count: number;
  failed_count: number;
  stalled_count: number;
  oldest_backlog_age_seconds: number | null;
  last_healthy_at: string | null;
}

export interface OperationsActiveVersion {
  kind: string;
  component: string;
  name: string;
  version: string;
  revision: string | null;
  numeric_value: number | null;
  source: string;
  observed_at: string;
}

export interface OperationsOverview {
  generated_at: string;
  stalled_after_seconds: number;
  total_backlog_count: number;
  total_stalled_count: number;
  queues: OperationsQueueSnapshot[];
  processing: OperationsProcessingSnapshot[];
  active_versions: OperationsActiveVersion[];
}

export interface OperationsFailureSummary {
  component: string;
  failed_count: number;
  partial_success_count: number;
  retry_count: number;
  stalled_count: number;
  oldest_signal_at: string | null;
  latest_signal_at: string | null;
  last_healthy_at: string | null;
  top_failure_codes: Array<{ code: string; count: number }>;
}

export interface OperationsFailures {
  generated_at: string;
  lookback_seconds: number;
  total_failed_count: number;
  total_partial_success_count: number;
  total_retry_count: number;
  total_stalled_count: number;
  components: OperationsFailureSummary[];
}

export interface OnboardingReadinessGate {
  code: string;
  status: "PASS" | "FAIL";
  description: string;
}

export interface OnboardingReadiness {
  pilot_ready: boolean;
  gates: OnboardingReadinessGate[];
}

export interface OperatorQueueParams {
  view: OperatorQueueView;
  sort: OperatorQueueSort;
  q?: string;
  limit?: number;
  cursor?: string;
}

export type RunStatus =
  | "QUEUED"
  | "PENDING"
  | "RUNNING"
  | "RETRY_WAITING"
  | "SUCCEEDED"
  | "PARTIAL_SUCCESS"
  | "FAILED"
  | string;

export interface AnalysisRun {
  analysis_run_id: string;
  tenant_id: string;
  case_id: string;
  pipeline: string;
  pipeline_version: string;
  trigger: string;
  status: RunStatus;
  requested_by: string;
  requested_at: string;
  started_at: string | null;
  completed_at: string | null;
  failure: { code: string; retryable: boolean } | null;
  created_at: string;
  updated_at: string;
}

export interface AnalysisDetail {
  run: AnalysisRun;
  stages: Array<Record<string, unknown> & {
    stage_run_id: string;
    stage_type: string;
    status: RunStatus;
    model_name: string;
    model_version: string;
    prompt_version: string;
    attempt_count: number;
  }>;
  extraction_result: Record<string, unknown> | null;
  extraction_result_v2: (Record<string, unknown> & {
    extraction_result_id?: string;
    schema_version?: string;
    requested_actions?: unknown[];
    system_missing_information?: unknown[];
    action_consistency?: string;
  }) | null;
  vision_results: Array<Record<string, unknown>>;
  failed_stages: string[];
}

export interface AsyncRun {
  id: string;
  case_id: string;
  status: RunStatus;
  created_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
  failure_code?: string | null;
  failure_message?: string | null;
  [key: string]: unknown;
}

export interface PolicyRetrievalRun extends AsyncRun {
  analysis_run_id: string;
  strategy: string;
  as_of_date: string;
  top_k: number;
  correlation_id: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  failure_code: string | null;
  failure_message: string | null;
}

export interface GroundingRun extends AsyncRun {
  retrieval_run_id: string;
  citation_pack_id: string;
  correlation_id: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  failure_code: string | null;
  failure_message: string | null;
}

export interface PolicyEvaluationRun extends AsyncRun {
  analysis_run_id: string;
  summary_status: string | null;
  rule_set: Record<string, string>;
  as_of_date: string;
  correlation_id: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  failure_code: string | null;
  failure_message: string | null;
}

export interface RetrievalDetail {
  run: PolicyRetrievalRun;
  query_plan: Record<string, unknown> | null;
  retrieval_profile: Record<string, unknown>;
  hits: Array<Record<string, unknown> & {
    rank?: number;
    clause_id?: string;
    document_id?: string;
    document_version?: string;
  }>;
}

export interface PolicyCitationSnapshot {
  citation_id: string;
  rank: number;
  policy_clause_id: string;
  document_id: string;
  document_version: string;
  title: string;
  section_path: string[];
  clause_type: string;
  text: string;
}

export interface PolicyCitationPack extends Record<string, unknown> {
  citations: PolicyCitationSnapshot[];
}

export interface GroundingDetail {
  run: GroundingRun;
  citation_pack: PolicyCitationPack;
  explanation: Record<string, unknown> | null;
  structural_validation: Record<string, unknown> | null;
  semantic_evaluation_status: string;
}

export interface PolicyDetail {
  run: PolicyEvaluationRun;
  input_qualification: Record<string, string>;
  rule_results: Array<Record<string, unknown>>;
}

export type ReviewTaskStatus =
  | "PENDING"
  | "CLAIMED"
  | "WAITING_FOR_EVIDENCE"
  | "ESCALATED"
  | "RESOLVED"
  | string;

export interface ReviewTask {
  id: string;
  case_id: string;
  policy_evaluation_run_id: string;
  task_type: string;
  priority: string;
  status: ReviewTaskStatus;
  current_assignee_id: string | null;
  version: number;
  mapping_rule_name: string;
  mapping_rule_version: string;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export interface ReviewAssignee {
  user_id: string;
  display_name: string;
  email: string;
  roles: string[];
}

export interface PolicySimilarityEvidence extends Record<string, unknown> {
  group: "NEAREST" | "LEAST";
  rank: number;
  cosine_similarity: number;
  reference_threshold: number;
  threshold_version: string;
  reason_codes: string[];
  policy_clause_id: string;
  title: string;
  text: string;
}

export interface ReviewTaskDetail {
  task: ReviewTask;
  packet: Record<string, unknown>;
  actions: Array<Record<string, unknown>>;
  decision: Record<string, unknown> | null;
  rule_results: Array<Record<string, unknown>>;
  citation_items: Array<Record<string, unknown>>;
  grounded_explanation: Record<string, unknown> | null;
  inquiry_summary: string | null;
  policy_similarity: PolicySimilarityEvidence[];
}

export interface ReviewActionResult {
  task: ReviewTask;
  decision: Record<string, unknown> | null;
}

export interface ResolutionView {
  id: string;
  case_id: string;
  source_review_task_id: string;
  source_human_decision_id: string;
  status: string;
  version: number;
  mapping_name: string;
  mapping_version: string;
  resolution_schema_version: string;
  missing_fields: string[];
  invalid_fields: string[];
  failure_code: string | null;
  failure_message: string | null;
  correlation_id: string;
  created_at: string;
  updated_at: string;
}

export interface ExternalActionIntent {
  id: string;
  case_id: string;
  resolution_id: string;
  human_decision_id: string;
  action_type: string;
  mode: string;
  order_ref: string;
  product_ref?: string | null;
  amount?: string | null;
  currency?: string | null;
  quantity?: number | null;
  shipping_address_ref?: string | null;
  mapping_name: string;
  mapping_version: string;
  intent_schema_version: string;
  content_hash: string;
  created_at: string;
  [key: string]: unknown;
}

export interface ExternalActionSimulationAttempt {
  id: string;
  case_id: string;
  resolution_id: string;
  external_action_intent_id: string;
  attempt_number: number;
  status: string;
  mode: string;
  started_at: string;
  completed_at: string | null;
  failure_code: string | null;
  failure_message: string | null;
}

export interface ExternalActionSimulationResult {
  id: string;
  case_id: string;
  resolution_id: string;
  external_action_intent_id: string;
  simulation_attempt_id: string;
  outcome: string;
  mode: string;
  side_effects_performed: boolean;
  failure_code: string | null;
  failure_message: string | null;
  simulated_request: Record<string, unknown>;
  simulated_response: Record<string, unknown>;
  result_schema_version: string;
  content_hash: string;
  created_at: string;
}

export interface ExternalActionIntentDetail {
  intent: ExternalActionIntent;
  attempts: ExternalActionSimulationAttempt[];
  results: ExternalActionSimulationResult[];
}

export interface ReviewReport {
  schema_version: string;
  report_id: string;
  case_id: string;
  resolution_id: string;
  resolution_version: number;
  terminal_event_id: string;
  case_snapshot: Record<string, unknown>;
  analysis_snapshot: Record<string, unknown>;
  policy_snapshot: Record<string, unknown>;
  review_snapshot: Record<string, unknown>;
  resolution_snapshot: Record<string, unknown>;
  dry_run_snapshot: Record<string, unknown>;
  qualification_snapshot: Record<string, unknown>;
  data_scope: Record<string, unknown>;
  generated_at: string;
  content_hash: string;
}

export interface RatioMetric {
  numerator: number;
  denominator: number;
  sample_count: number;
  value: number | null;
  unit: "ratio" | "seconds" | string;
}

export interface PocSummary {
  schema_version: string;
  generated_at: string;
  eligible_source_scope: "PILOT_LIVE";
  eligible_case_count: number;
  excluded_case_count: number;
  review_time: RatioMetric;
  recommendation_difference_rate: RatioMetric;
  additional_evidence_request_rate: RatioMetric;
  action_input_missing_rate: RatioMetric;
  dry_run_success_rate: RatioMetric;
  analysis_failure_rate: RatioMetric;
  analysis_partial_success_rate: RatioMetric;
}

export interface CustomerCommunicationSimulation {
  schema_version: string;
  communication_id: string;
  case_id: string;
  review_report_id: string;
  channel: string;
  template_name: string;
  template_version: string;
  recipient_label: string;
  subject: string;
  body: string;
  delivery_status: string;
  side_effects_performed: boolean;
  created_at: string;
  content_hash: string;
}

export interface CaseLearningAsset {
  schema_version: string;
  asset_id: string;
  case_id: string;
  review_report_id: string;
  feature_snapshot: Record<string, unknown>;
  label_snapshot: Record<string, unknown>;
  version_snapshot: Record<string, unknown>;
  privacy_scope: Record<string, unknown>;
  created_at: string;
  content_hash: string;
}

export interface DataAssetSummary {
  schema_version: string;
  generated_at: string;
  total_records: number;
  eligible_records: number;
  excluded_records: number;
  eligible_source_scope: "PILOT_LIVE";
  source_scope_distribution: Record<string, number>;
  baseline_minimum: number;
  drift_review_minimum: number;
  readiness_status: string;
  drift_evaluation_available: boolean;
  decision_distribution: Record<string, number>;
  resolution_distribution: Record<string, number>;
  product_distribution: Record<string, number>;
  model_version_distribution: Record<string, number>;
  policy_version_distribution: Record<string, number>;
  recent_records: CaseLearningAsset[];
}

export interface ApiProblem {
  status: number;
  code: string;
  message: string;
  details?: unknown;
}
