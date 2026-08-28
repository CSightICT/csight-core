import type {
  AnalysisRun,
  GroundingRun,
  PolicyEvaluationRun,
  PolicyRetrievalRun,
} from "../api/contracts";

const TEXT_PIPELINE = "product_defect_text_extraction";
const TEXT_V2_VERSION = "2.0.0";
const VISION_PIPELINE = "product_defect_multimodal_analysis";

export interface LatestCaseAnalysisRuns {
  textV2RunId: string | null;
  visionRunId: string | null;
}

export interface LatestPolicyRunSet {
  retrievalRunId: string | null;
  groundingRunId: string | null;
  policyEvaluationRunId: string | null;
}

export interface PolicyRunPreferences {
  retrievalRunId?: string;
  groundingRunId?: string;
  policyEvaluationRunId?: string;
}

const COMPLETED_SUCCESS = new Set(["SUCCEEDED", "COMPLETED"]);
const ACTIVE_RUN = new Set(["QUEUED", "PENDING", "RUNNING", "RETRY_WAITING"]);
const TEXT_USABLE = new Set([...COMPLETED_SUCCESS, ...ACTIVE_RUN]);
const VISION_USABLE = new Set([...TEXT_USABLE, "PARTIAL_SUCCESS"]);

function timestamp(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}

function compareNewest(left: AnalysisRun, right: AnalysisRun): number {
  const requestedDifference = timestamp(left.requested_at) - timestamp(right.requested_at);
  if (requestedDifference !== 0) return requestedDifference;
  const createdDifference = timestamp(left.created_at) - timestamp(right.created_at);
  if (createdDifference !== 0) return createdDifference;
  return left.analysis_run_id.localeCompare(right.analysis_run_id);
}

function latestMatching(
  runs: AnalysisRun[],
  matches: (run: AnalysisRun) => boolean,
): AnalysisRun | null {
  return runs.reduce<AnalysisRun | null>((latest, candidate) => {
    if (!matches(candidate)) return latest;
    return latest === null || compareNewest(candidate, latest) > 0 ? candidate : latest;
  }, null);
}

export function findLatestCaseAnalysisRuns(runs: AnalysisRun[]): LatestCaseAnalysisRuns {
  const textV2 = latestMatching(
    runs,
    (run) => run.pipeline === TEXT_PIPELINE
      && run.pipeline_version === TEXT_V2_VERSION
      && TEXT_USABLE.has(run.status),
  );
  const vision = latestMatching(
    runs,
    (run) => run.pipeline === VISION_PIPELINE && VISION_USABLE.has(run.status),
  );
  return {
    textV2RunId: textV2?.analysis_run_id ?? null,
    visionRunId: vision?.analysis_run_id ?? null,
  };
}

interface DatedRun {
  id: string;
  created_at: string;
}

function compareDatedNewest(left: DatedRun, right: DatedRun): number {
  const createdDifference = timestamp(left.created_at) - timestamp(right.created_at);
  if (createdDifference !== 0) return createdDifference;
  return left.id.localeCompare(right.id);
}

function latestDated<T extends DatedRun>(runs: T[]): T | null {
  return runs.reduce<T | null>(
    (latest, candidate) => latest === null || compareDatedNewest(candidate, latest) > 0
      ? candidate
      : latest,
    null,
  );
}

function completed(status: string): boolean {
  return COMPLETED_SUCCESS.has(status);
}

function active(status: string): boolean {
  return ACTIVE_RUN.has(status);
}

function recoverable(status: string): boolean {
  return completed(status) || active(status);
}

/**
 * Recovers only server-verified links. Active runs take precedence so a cold
 * session resumes or blocks on the server-owned run instead of issuing a
 * duplicate POST. When nothing is active, a completed retrieval with completed
 * grounding is preferred over a newer incomplete completed retrieval.
 */
export function findLatestPolicyRunSet(
  analysisRunId: string,
  retrievalRuns: PolicyRetrievalRun[],
  groundingRuns: GroundingRun[],
  policyRuns: PolicyEvaluationRun[],
  preferences: PolicyRunPreferences = {},
): LatestPolicyRunSet {
  const anchoredRetrievals = retrievalRuns.filter(
    (run) => run.analysis_run_id === analysisRunId && recoverable(run.status),
  );
  const recoverableGroundings = groundingRuns.filter((run) => recoverable(run.status));

  let retrieval: PolicyRetrievalRun | null;
  if (preferences.retrievalRunId) {
    retrieval = anchoredRetrievals.find((run) => run.id === preferences.retrievalRunId) ?? null;
  } else {
    const anchoredRetrievalIds = new Set(anchoredRetrievals.map((run) => run.id));
    const activeGrounding = latestDated(recoverableGroundings.filter(
      (run) => active(run.status) && anchoredRetrievalIds.has(run.retrieval_run_id),
    ));
    const activeRetrieval = latestDated(anchoredRetrievals.filter((run) => active(run.status)));
    const completedGroundedRetrievalIds = new Set(
      recoverableGroundings
        .filter((run) => completed(run.status))
        .map((run) => run.retrieval_run_id),
    );
    retrieval = activeGrounding
      ? anchoredRetrievals.find((run) => run.id === activeGrounding.retrieval_run_id) ?? null
      : activeRetrieval
        ?? latestDated(anchoredRetrievals.filter(
          (run) => completed(run.status) && completedGroundedRetrievalIds.has(run.id),
        ))
        ?? latestDated(anchoredRetrievals.filter((run) => completed(run.status)));
  }

  const linkedGroundings = retrieval
    ? recoverableGroundings.filter((run) => run.retrieval_run_id === retrieval.id)
    : [];
  const grounding = preferences.groundingRunId
    ? linkedGroundings.find((run) => run.id === preferences.groundingRunId) ?? null
    : latestDated(linkedGroundings.filter((run) => active(run.status)))
      ?? latestDated(linkedGroundings.filter((run) => completed(run.status)));

  const anchoredPolicies = policyRuns.filter(
    (run) => run.analysis_run_id === analysisRunId && recoverable(run.status),
  );
  const policy = preferences.policyEvaluationRunId
    ? anchoredPolicies.find((run) => run.id === preferences.policyEvaluationRunId) ?? null
    : latestDated(anchoredPolicies.filter((run) => active(run.status)))
      ?? latestDated(anchoredPolicies.filter((run) => completed(run.status)));

  return {
    retrievalRunId: retrieval?.id ?? null,
    groundingRunId: grounding?.id ?? null,
    policyEvaluationRunId: policy?.id ?? null,
  };
}
