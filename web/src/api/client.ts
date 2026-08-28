import {
  decodeAnalysisDetail,
  decodeAnalysisRun,
  decodeCaseDetail,
  decodeCasePage,
  decodeCustomerCommunication,
  decodeCustomerCommunications,
  decodeCurrentUser,
  decodeDataAssetSummary,
  decodeEvidenceAccessUrl,
  decodeGroundingDetail,
  decodeGroundingRuns,
  decodeIntentDetail,
  decodeIntentList,
  decodePocSummary,
  decodePolicyDetail,
  decodePolicyEvaluationRuns,
  decodePolicyRetrievalRuns,
  decodeResolution,
  decodeRetrievalDetail,
  decodeReviewActionResult,
  decodeReviewReport,
  decodeReviewTaskDetail,
  decodeReviewTasks,
  decodeToken,
} from "./decoders";
import type {
  AnalysisDetail,
  AnalysisRun,
  ApiProblem,
  CaseDetail,
  CasePage,
  CustomerCommunicationSimulation,
  CurrentUser,
  DataAssetSummary,
  Evidence,
  EvidenceAccessUrl,
  ExternalActionIntent,
  ExternalActionIntentDetail,
  GroundingDetail,
  GroundingRun,
  PocSummary,
  PolicyDetail,
  PolicyEvaluationRun,
  PolicyRetrievalRun,
  ResolutionView,
  RetrievalDetail,
  ReviewActionResult,
  ReviewReport,
  ReviewTask,
  ReviewTaskDetail,
  TokenResponse,
} from "./contracts";
import { tokenVault } from "../auth/tokenVault";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(problem: ApiProblem) {
    super(problem.message);
    this.name = "ApiError";
    this.status = problem.status;
    this.code = problem.code;
    this.details = problem.details;
  }
}

type SessionExpiredListener = () => void;
const expiredListeners = new Set<SessionExpiredListener>();

export function onSessionExpired(listener: SessionExpiredListener): () => void {
  expiredListeners.add(listener);
  return () => expiredListeners.delete(listener);
}

function emitSessionExpired(): void {
  tokenVault.clear();
  expiredListeners.forEach((listener) => listener());
}

async function parseError(response: Response): Promise<ApiError> {
  let body: unknown;
  try { body = await response.json(); } catch { body = undefined; }
  const root = body && typeof body === "object" ? body as Record<string, unknown> : {};
  const error = root.error;
  const detail = root.detail;
  const structured = error && typeof error === "object"
    ? error as Record<string, unknown>
    : detail && typeof detail === "object" && !Array.isArray(detail)
      ? detail as Record<string, unknown>
      : {};
  const message = typeof structured.message === "string"
    ? structured.message
    : typeof detail === "string"
      ? detail
      : `요청을 처리하지 못했습니다 (${response.status}).`;
  const code = typeof structured.code === "string" ? structured.code : `HTTP_${response.status}`;
  return new ApiError({ status: response.status, code, message, details: body });
}

interface RequestOptions extends RequestInit {
  auth?: boolean;
  idempotencyKey?: string;
}

async function request(path: string, options: RequestOptions = {}): Promise<unknown> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (options.auth !== false) {
    const token = tokenVault.get();
    if (!token) {
      emitSessionExpired();
      throw new ApiError({ status: 401, code: "SESSION_EXPIRED", message: "다시 로그인해 주세요." });
    }
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (options.idempotencyKey) headers.set("Idempotency-Key", options.idempotencyKey);
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    if (response.status === 401 && options.auth !== false) emitSessionExpired();
    throw await parseError(response);
  }
  if (response.status === 204) return undefined;
  return response.json();
}

async function requestImageBlob(path: string): Promise<Blob> {
  const token = tokenVault.get();
  if (!token) {
    emitSessionExpired();
    throw new ApiError({ status: 401, code: "SESSION_EXPIRED", message: "다시 로그인해 주세요." });
  }
  const response = await fetch(path, {
    method: "GET",
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    if (response.status === 401) emitSessionExpired();
    throw await parseError(response);
  }
  const contentType = response.headers.get("Content-Type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (!contentType || !["image/jpeg", "image/png", "image/webp"].includes(contentType)) {
    throw new ApiError({
      status: 502,
      code: "EVIDENCE_CONTENT_TYPE_INVALID",
      message: "증거 이미지 응답 형식을 확인할 수 없습니다.",
    });
  }
  const content = await response.blob();
  if (content.size === 0) {
    throw new ApiError({
      status: 502,
      code: "EVIDENCE_CONTENT_EMPTY",
      message: "증거 이미지 응답이 비어 있습니다.",
    });
  }
  return content;
}

const json = (value: unknown): string => JSON.stringify(value);

export interface CreateCaseInput {
  order_ref: string;
  product_ref: string;
  customer_message: string;
  requested_action: string;
  attributes: Record<string, unknown>;
}

export interface ResolveInput {
  expected_version: number;
  decision: string;
  reason_codes: string[];
  rationale: string;
  basis: Array<{ type: string; reference_id: string }>;
}

export const api = {
  async login(input: { tenant_slug: string; email: string; password: string }): Promise<TokenResponse> {
    return decodeToken(await request("/api/v1/auth/token", {
      method: "POST", auth: false, body: json(input),
    }));
  },
  async me(): Promise<CurrentUser> {
    return decodeCurrentUser(await request("/api/v1/auth/me"));
  },
  async listCases(search = ""): Promise<CasePage> {
    return decodeCasePage(await request(`/api/v1/cases${search}`));
  },
  async getCase(caseId: string): Promise<CaseDetail> {
    return decodeCaseDetail(await request(`/api/v1/cases/${encodeURIComponent(caseId)}`));
  },
  async createCase(input: CreateCaseInput, key: string): Promise<{ case_id: string; status: string; created_at: string }> {
    return await request("/api/v1/cases", { method: "POST", idempotencyKey: key, body: json(input) }) as {
      case_id: string; status: string; created_at: string;
    };
  },
  async uploadEvidence(caseId: string, file: File): Promise<Evidence> {
    const form = new FormData();
    form.append("file", file);
    form.append("evidence_type", "IMAGE");
    return await request(`/api/v1/cases/${encodeURIComponent(caseId)}/evidence`, {
      method: "POST", body: form,
    }) as Evidence;
  },
  async getEvidenceAccessUrl(caseId: string, evidenceId: string): Promise<EvidenceAccessUrl> {
    const value = decodeEvidenceAccessUrl(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}/access-url`, {
      method: "POST",
    }));
    if (value.evidence_id !== evidenceId) {
      throw new ApiError({
        status: 502,
        code: "EVIDENCE_ACCESS_ID_MISMATCH",
        message: "증거 미리보기 응답의 식별자가 요청과 일치하지 않습니다.",
      });
    }
    return value;
  },
  async getEvidenceContent(caseId: string, evidenceId: string): Promise<Blob> {
    return requestImageBlob(`/api/v1/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}/content`);
  },
  async startAnalysis(caseId: string, pipeline: string, pipelineVersion: string, key: string): Promise<AnalysisRun> {
    return decodeAnalysisRun(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/analysis-runs`, {
      method: "POST", idempotencyKey: key, body: json({ pipeline, pipeline_version: pipelineVersion }),
    }));
  },
  async getAnalysis(caseId: string, runId: string): Promise<AnalysisDetail> {
    return decodeAnalysisDetail(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/analysis-runs/${encodeURIComponent(runId)}`));
  },
  async listAnalysis(caseId: string): Promise<AnalysisRun[]> {
    const value = await request(`/api/v1/cases/${encodeURIComponent(caseId)}/analysis-runs?page=1&page_size=100`) as { items?: unknown[] };
    return Array.isArray(value.items) ? value.items.map(decodeAnalysisRun) : [];
  },
  async startRetrieval(caseId: string, analysisRunId: string, asOfDate: string, key: string): Promise<{ id: string; status: string }> {
    return await request(`/api/v1/cases/${encodeURIComponent(caseId)}/policy-retrieval-runs`, {
      method: "POST", idempotencyKey: key,
      body: json({ analysis_run_id: analysisRunId, strategy: "RAW", as_of_date: asOfDate, top_k: 3 }),
    }) as { id: string; status: string };
  },
  async getRetrieval(caseId: string, runId: string): Promise<RetrievalDetail> {
    return decodeRetrievalDetail(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/policy-retrieval-runs/${encodeURIComponent(runId)}`));
  },
  async listRetrieval(caseId: string): Promise<PolicyRetrievalRun[]> {
    return decodePolicyRetrievalRuns(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/policy-retrieval-runs`));
  },
  async startGrounding(caseId: string, retrievalRunId: string, key: string): Promise<{ id: string; status: string }> {
    return await request(`/api/v1/cases/${encodeURIComponent(caseId)}/grounded-explanation-runs`, {
      method: "POST", idempotencyKey: key, body: json({ retrieval_run_id: retrievalRunId }),
    }) as { id: string; status: string };
  },
  async getGrounding(caseId: string, runId: string): Promise<GroundingDetail> {
    return decodeGroundingDetail(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/grounded-explanation-runs/${encodeURIComponent(runId)}`));
  },
  async listGrounding(caseId: string): Promise<GroundingRun[]> {
    return decodeGroundingRuns(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/grounded-explanation-runs`));
  },
  async startPolicy(caseId: string, analysisRunId: string, asOfDate: string, key: string): Promise<{ policy_evaluation_run_id: string; status: string }> {
    return await request(`/api/v1/cases/${encodeURIComponent(caseId)}/policy-evaluation-runs`, {
      method: "POST", idempotencyKey: key, body: json({ analysis_run_id: analysisRunId, as_of_date: asOfDate }),
    }) as { policy_evaluation_run_id: string; status: string };
  },
  async getPolicy(caseId: string, runId: string): Promise<PolicyDetail> {
    return decodePolicyDetail(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/policy-evaluation-runs/${encodeURIComponent(runId)}`));
  },
  async listPolicy(caseId: string): Promise<PolicyEvaluationRun[]> {
    return decodePolicyEvaluationRuns(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/policy-evaluation-runs`));
  },
  async listReviewTasks(query = ""): Promise<ReviewTask[]> {
    return decodeReviewTasks(await request(`/api/v1/human-review-tasks${query}`));
  },
  async listCaseReviewTasks(caseId: string): Promise<ReviewTask[]> {
    return decodeReviewTasks(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/human-review-tasks`));
  },
  async getReviewTask(taskId: string): Promise<ReviewTaskDetail> {
    return decodeReviewTaskDetail(await request(`/api/v1/human-review-tasks/${encodeURIComponent(taskId)}`));
  },
  async reviewAction(taskId: string, action: string, body: Record<string, unknown>): Promise<ReviewActionResult> {
    return decodeReviewActionResult(await request(`/api/v1/human-review-tasks/${encodeURIComponent(taskId)}/${action}`, {
      method: "POST", body: json(body),
    }));
  },
  async resolveReview(taskId: string, body: ResolveInput): Promise<ReviewActionResult> {
    return this.reviewAction(taskId, "resolve", { ...body });
  },
  async getResolution(caseId: string): Promise<ResolutionView> {
    return decodeResolution(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/resolution`));
  },
  async listResolutionEvents(caseId: string): Promise<Array<Record<string, unknown>>> {
    const value = await request(`/api/v1/cases/${encodeURIComponent(caseId)}/resolution/events`) as unknown;
    return Array.isArray(value) ? value as Array<Record<string, unknown>> : ((value as { items?: Array<Record<string, unknown>> }).items ?? []);
  },
  async listIntents(caseId: string): Promise<ExternalActionIntent[]> {
    return decodeIntentList(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/external-action-intents`));
  },
  async getIntent(intentId: string): Promise<ExternalActionIntentDetail> {
    return decodeIntentDetail(await request(`/api/v1/external-action-intents/${encodeURIComponent(intentId)}`));
  },
  async getReport(caseId: string): Promise<ReviewReport> {
    return decodeReviewReport(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/review-report`));
  },
  async getMetrics(): Promise<PocSummary> {
    return decodePocSummary(await request("/api/v1/metrics/poc-summary"));
  },
  async createCustomerCommunication(caseId: string): Promise<CustomerCommunicationSimulation> {
    return decodeCustomerCommunication(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/communication-simulations`, { method: "POST" }));
  },
  async listCustomerCommunications(caseId: string): Promise<CustomerCommunicationSimulation[]> {
    return decodeCustomerCommunications(await request(`/api/v1/cases/${encodeURIComponent(caseId)}/communication-simulations`));
  },
  async getDataAssetSummary(): Promise<DataAssetSummary> {
    return decodeDataAssetSummary(await request("/api/v1/data-assets/summary"));
  },
};
