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
  isExactE3Identity: boolean;
}

const E3_IDENTITY = {
  providerName: "remote_vision",
  modelName: "csight-dinov2-vits14-kaputt-binary",
  modelVersion: "e3-epoch10-20260827",
  modelRevision: "49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e",
  taxonomyVersion: "csight-any-defect-assessment-v1",
  thresholdVersion: "1.0",
  preprocessVersion: "1.0",
  postprocessVersion: "sigmoid-any-defect-v1",
  threshold: 0.8984375,
} as const;

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

    const detections = result.detections;
    const {
      assessment_type: assessmentType,
      model_output_name: modelOutputName,
      score,
      threshold,
      threshold_operator: thresholdOperator,
      outcome,
    } = assessment;
    if (
      result.schema_version !== "1.0"
      || !Array.isArray(detections)
      || detections.length !== 0
      || assessmentType !== "ANY_DEFECT"
      || modelOutputName !== "defect"
      || thresholdOperator !== "GREATER_THAN_OR_EQUAL"
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
    const isExactE3Identity = providerName === E3_IDENTITY.providerName
      && modelName === E3_IDENTITY.modelName
      && result.model_version === E3_IDENTITY.modelVersion
      && result.model_revision === E3_IDENTITY.modelRevision
      && result.taxonomy_version === E3_IDENTITY.taxonomyVersion
      && result.threshold_version === E3_IDENTITY.thresholdVersion
      && result.preprocess_version === E3_IDENTITY.preprocessVersion
      && result.postprocess_version === E3_IDENTITY.postprocessVersion
      && threshold === E3_IDENTITY.threshold;
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
      isExactE3Identity,
    }];
  });
}

export function formatVisionProbability(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

export function describeVisionQualification(
  qualification: BinaryVisionAssessmentView["qualification"],
): string {
  if (qualification === "SYNTHETIC_MOCK") return "합성 Mock · 연결 검증 전용";
  if (qualification === "REMOTE_UNQUALIFIED") return "원격 추론 · 제품 적격성 미확인";
  return "Provider 적격성 확인 불가";
}
