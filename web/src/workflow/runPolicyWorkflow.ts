import type { AnalysisDetail, GroundingDetail, PolicyDetail, RetrievalDetail, ReviewTask } from "../api/contracts";
import { checkpointStore, newOpaqueKey, type WorkflowCheckpoint } from "../recovery/workflowCheckpoint";

const TERMINAL = new Set(["SUCCEEDED", "PARTIAL_SUCCESS", "FAILED"]);
const SUCCESS = new Set(["SUCCEEDED", "COMPLETED"]);

export interface WorkflowApi {
  startAnalysis(caseId: string, pipeline: string, version: string, key: string): Promise<{ analysis_run_id: string }>;
  getAnalysis(caseId: string, runId: string): Promise<AnalysisDetail>;
  startRetrieval(caseId: string, analysisId: string, asOfDate: string, key: string): Promise<{ id: string }>;
  getRetrieval(caseId: string, runId: string): Promise<RetrievalDetail>;
  startGrounding(caseId: string, retrievalId: string, key: string): Promise<{ id: string }>;
  getGrounding(caseId: string, runId: string): Promise<GroundingDetail>;
  startPolicy(caseId: string, analysisId: string, asOfDate: string, key: string): Promise<{ policy_evaluation_run_id: string }>;
  getPolicy(caseId: string, runId: string): Promise<PolicyDetail>;
  listCaseReviewTasks(caseId: string): Promise<ReviewTask[]>;
}

export type WorkflowStage = "TEXT_V2" | "RAW_TOP3" | "GROUNDING" | "POLICY" | "REVIEW";
export interface WorkflowProgress { stage: WorkflowStage; status: string; message: string }
export interface WorkflowResult {
  checkpoint: WorkflowCheckpoint;
  analysis: AnalysisDetail;
  retrieval: RetrievalDetail;
  grounding: GroundingDetail;
  policy: PolicyDetail;
  reviewTask: ReviewTask | null;
}

export interface WorkflowOptions {
  pollMs?: number;
  maxPolls?: number;
  onProgress?: (progress: WorkflowProgress) => void;
  signal?: AbortSignal;
}

function requireActive(signal?: AbortSignal): void {
  if (signal?.aborted) throw new DOMException("Workflow cancelled", "AbortError");
}

async function pause(ms: number, signal?: AbortSignal): Promise<void> {
  if (ms <= 0) return;
  await new Promise<void>((resolve, reject) => {
    const id = window.setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      window.clearTimeout(id);
      reject(new DOMException("Workflow cancelled", "AbortError"));
    }, { once: true });
  });
}

function assertSucceeded(stage: string, status: string): void {
  if (!SUCCESS.has(status)) throw new Error(`${stage} 단계가 ${status} 상태로 종료되어 다음 단계로 진행하지 않았습니다.`);
}

async function poll<T>(
  load: () => Promise<T>,
  statusOf: (value: T) => string,
  options: { pollMs: number; maxPolls: number; signal: AbortSignal | undefined },
): Promise<T> {
  for (let count = 0; count < options.maxPolls; count += 1) {
    requireActive(options.signal);
    const value = await load();
    const status = statusOf(value);
    if (TERMINAL.has(status) || SUCCESS.has(status)) return value;
    await pause(options.pollMs, options.signal);
  }
  throw new Error("처리 시간이 예상보다 길어졌습니다. 저장된 실행 ID로 다시 확인해 주세요.");
}

export async function runPolicyWorkflow(
  client: WorkflowApi,
  caseId: string,
  asOfDate: string,
  options: WorkflowOptions = {},
): Promise<WorkflowResult> {
  const settings = { pollMs: options.pollMs ?? 1400, maxPolls: options.maxPolls ?? 180, signal: options.signal };
  let checkpoint = checkpointStore.load(caseId);

  const textKey = checkpoint.idempotencyKeys.analysisV2 ?? newOpaqueKey();
  if (!checkpoint.idempotencyKeys.analysisV2) {
    checkpoint = checkpointStore.patch(caseId, { idempotencyKeys: { ...checkpoint.idempotencyKeys, analysisV2: textKey } });
  }
  if (!checkpoint.analysisV2RunId) {
    options.onProgress?.({ stage: "TEXT_V2", status: "STARTING", message: "문의 내용을 구조화하고 있습니다." });
    const started = await client.startAnalysis(caseId, "product_defect_text_extraction", "2.0.0", textKey);
    checkpoint = checkpointStore.patch(caseId, { analysisV2RunId: started.analysis_run_id });
  }
  const analysis = await poll(
    () => client.getAnalysis(caseId, checkpoint.analysisV2RunId!),
    (value) => value.run.status,
    settings,
  );
  options.onProgress?.({ stage: "TEXT_V2", status: analysis.run.status, message: "텍스트 분석 결과를 확인했습니다." });
  assertSucceeded("텍스트 분석", analysis.run.status);

  const retrievalKey = checkpoint.idempotencyKeys.retrieval ?? newOpaqueKey();
  if (!checkpoint.retrievalRunId) {
    checkpoint = checkpointStore.patch(caseId, { idempotencyKeys: { ...checkpoint.idempotencyKeys, retrieval: retrievalKey } });
    options.onProgress?.({ stage: "RAW_TOP3", status: "STARTING", message: "원문 질의로 적용 정책 Top-3를 찾고 있습니다." });
    const started = await client.startRetrieval(caseId, checkpoint.analysisV2RunId!, asOfDate, retrievalKey);
    checkpoint = checkpointStore.patch(caseId, { retrievalRunId: started.id });
  }
  const retrieval = await poll(
    () => client.getRetrieval(caseId, checkpoint.retrievalRunId!),
    (value) => value.run.status,
    settings,
  );
  options.onProgress?.({ stage: "RAW_TOP3", status: retrieval.run.status, message: "정책 후보와 인용 근거를 찾았습니다." });
  assertSucceeded("정책 검색", retrieval.run.status);

  const groundingKey = checkpoint.idempotencyKeys.grounding ?? newOpaqueKey();
  if (!checkpoint.groundingRunId) {
    checkpoint = checkpointStore.patch(caseId, { idempotencyKeys: { ...checkpoint.idempotencyKeys, grounding: groundingKey } });
    options.onProgress?.({ stage: "GROUNDING", status: "STARTING", message: "정책 조항과 설명을 연결하고 있습니다." });
    const started = await client.startGrounding(caseId, checkpoint.retrievalRunId!, groundingKey);
    checkpoint = checkpointStore.patch(caseId, { groundingRunId: started.id });
  }
  const grounding = await poll(
    () => client.getGrounding(caseId, checkpoint.groundingRunId!),
    (value) => value.run.status,
    settings,
  );
  options.onProgress?.({ stage: "GROUNDING", status: grounding.run.status, message: "인용과 설명의 연결을 검증했습니다." });
  assertSucceeded("근거 연결", grounding.run.status);

  const policyKey = checkpoint.idempotencyKeys.policy ?? newOpaqueKey();
  if (!checkpoint.policyEvaluationRunId) {
    checkpoint = checkpointStore.patch(caseId, { idempotencyKeys: { ...checkpoint.idempotencyKeys, policy: policyKey } });
    options.onProgress?.({ stage: "POLICY", status: "STARTING", message: "버전이 고정된 정책 규칙을 평가하고 있습니다." });
    const started = await client.startPolicy(caseId, checkpoint.analysisV2RunId!, asOfDate, policyKey);
    checkpoint = checkpointStore.patch(caseId, { policyEvaluationRunId: started.policy_evaluation_run_id });
  }
  const policy = await poll(
    () => client.getPolicy(caseId, checkpoint.policyEvaluationRunId!),
    (value) => value.run.status,
    settings,
  );
  options.onProgress?.({ stage: "POLICY", status: policy.run.status, message: "정책 평가를 마쳤습니다." });
  assertSucceeded("정책 평가", policy.run.status);

  let reviewTask: ReviewTask | null = null;
  for (let count = 0; count < 12 && !reviewTask; count += 1) {
    const tasks = await client.listCaseReviewTasks(caseId);
    reviewTask = tasks.find((task) => task.policy_evaluation_run_id === checkpoint.policyEvaluationRunId) ?? null;
    if (!reviewTask) await pause(settings.pollMs, settings.signal);
  }
  options.onProgress?.({
    stage: "REVIEW", status: reviewTask ? reviewTask.status : "PENDING",
    message: reviewTask ? "사람 검토 작업이 준비됐습니다." : "검토 작업 생성이 지연되고 있습니다.",
  });
  return { checkpoint, analysis, retrieval, grounding, policy, reviewTask };
}
