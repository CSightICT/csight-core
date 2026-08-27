export interface BinaryVisionAssessmentView {
  evidenceId: string | null;
  providerName: string | null;
  modelName: string | null;
  datasetVersion: string | null;
  thresholdVersion: string | null;
  qualification: "SYNTHETIC_MOCK" | "REMOTE_UNQUALIFIED" | "UNKNOWN";
  assessmentType: "ANY_DEFECT";
  score: number;
  threshold: number;
  outcome:
    | "HIGH_CONFIDENCE_DEFECT_CANDIDATE"
    | "BELOW_HIGH_CONFIDENCE_THRESHOLD";
  isCandidate: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function readBinaryVisionAssessment(
  visionResults: Array<Record<string, unknown>>,
): BinaryVisionAssessmentView | null {
  const assessments = readBinaryVisionAssessments(visionResults);
  return assessments.length === 1 ? assessments[0]! : null;
}

export function readBinaryVisionAssessments(
  visionResults: Array<Record<string, unknown>>,
): BinaryVisionAssessmentView[] {
  return visionResults.flatMap((record) => {
    const result = record.result;
    if (!isRecord(result)) return [];
    const assessment = result.image_assessment;
    if (!isRecord(assessment)) return [];

    const { assessment_type: assessmentType, score, threshold, outcome } = assessment;
    if (
      assessmentType !== "ANY_DEFECT"
      || typeof score !== "number"
      || !Number.isFinite(score)
      || score < 0
      || score > 1
      || typeof threshold !== "number"
      || !Number.isFinite(threshold)
      || threshold < 0
      || threshold > 1
      || (outcome !== "HIGH_CONFIDENCE_DEFECT_CANDIDATE"
        && outcome !== "BELOW_HIGH_CONFIDENCE_THRESHOLD")
    ) return [];

    const isCandidate = score >= threshold;
    if (isCandidate !== (outcome === "HIGH_CONFIDENCE_DEFECT_CANDIDATE")) return [];
    const providerName = typeof result.provider_name === "string" ? result.provider_name : null;
    const modelName = typeof result.model_name === "string" ? result.model_name : null;
    const datasetVersion = typeof result.dataset_version === "string" ? result.dataset_version : null;
    const thresholdVersion = typeof result.threshold_version === "string" ? result.threshold_version : null;
    const evidenceId = typeof record.evidence_id === "string" ? record.evidence_id : null;
    const qualification = providerName === "mock" || datasetVersion?.startsWith("synthetic-")
      ? "SYNTHETIC_MOCK"
      : providerName === "remote_vision"
        ? "REMOTE_UNQUALIFIED"
        : "UNKNOWN";
    return [{
      evidenceId,
      providerName,
      modelName,
      datasetVersion,
      thresholdVersion,
      qualification,
      assessmentType,
      score,
      threshold,
      outcome,
      isCandidate,
    }];
  });
}

export function formatVisionProbability(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}
