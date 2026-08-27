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

export interface RetrievalDetail {
  run: AsyncRun & { analysis_run_id: string; strategy: string; top_k: number };
  query_plan: Record<string, unknown> | null;
  retrieval_profile: Record<string, unknown>;
  hits: Array<Record<string, unknown> & {
    rank?: number;
    clause_id?: string;
    document_id?: string;
    document_version?: string;
  }>;
}

export interface GroundingDetail {
  run: AsyncRun & { retrieval_run_id: string; citation_pack_id: string };
  citation_pack: Record<string, unknown>;
  explanation: Record<string, unknown> | null;
  structural_validation: Record<string, unknown> | null;
  semantic_evaluation_status: string;
}

export interface PolicyDetail {
  run: AsyncRun & {
    analysis_run_id: string;
    summary_status?: string | null;
    rule_set?: Record<string, string>;
  };
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

export interface ReviewTaskDetail {
  task: ReviewTask;
  packet: Record<string, unknown>;
  actions: Array<Record<string, unknown>>;
  decision: Record<string, unknown> | null;
  rule_results: Array<Record<string, unknown>>;
  citation_items: Array<Record<string, unknown>>;
  grounded_explanation: Record<string, unknown> | null;
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
  review_time: RatioMetric;
  recommendation_difference_rate: RatioMetric;
  additional_evidence_request_rate: RatioMetric;
  action_input_missing_rate: RatioMetric;
  dry_run_success_rate: RatioMetric;
  analysis_failure_rate: RatioMetric;
  analysis_partial_success_rate: RatioMetric;
}

export interface ApiProblem {
  status: number;
  code: string;
  message: string;
  details?: unknown;
}
