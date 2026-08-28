import { describe, expect, it } from "vitest";

import {
  describeVisionQualification,
  formatVisionProbability,
  readBinaryVisionAssessment,
  readBinaryVisionAssessments,
} from "./imageAssessment";

describe("binary Vision assessment presentation", () => {
  it("presents a threshold candidate without inventing localization", () => {
    const result = readBinaryVisionAssessment([{
      result: {
        schema_version: "1.0",
        detections: [],
        image_assessment: {
          assessment_type: "ANY_DEFECT",
          model_output_name: "defect",
          score: 0.94,
          threshold: 0.8984375,
          threshold_operator: "GREATER_THAN_OR_EQUAL",
          outcome: "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
        },
      },
    }]);

    expect(result).toEqual({
      evidenceId: null,
      providerName: null,
      modelName: null,
      datasetVersion: null,
      thresholdVersion: null,
      qualification: "UNKNOWN",
      assessmentType: "ANY_DEFECT",
      score: 0.94,
      threshold: 0.8984375,
      outcome: "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
      isCandidate: true,
      isExactE3Identity: false,
    });
    expect(formatVisionProbability(result!.threshold)).toBe("89.84%");
  });

  it("keeps every image assessment and separates Mock from remote qualification", () => {
    const baseAssessment = {
      assessment_type: "ANY_DEFECT",
      model_output_name: "defect",
      score: 0.94,
      threshold: 0.8984375,
      threshold_operator: "GREATER_THAN_OR_EQUAL",
      outcome: "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
    };
    const results = readBinaryVisionAssessments([
      {
        evidence_id: "evidence-mock",
        result: {
          schema_version: "1.0",
          provider_name: "mock",
          model_name: "contract-mock",
          dataset_version: "synthetic-any-defect-v1",
          threshold_version: "synthetic-threshold-v1",
          detections: [],
          image_assessment: baseAssessment,
        },
      },
      {
        evidence_id: "evidence-remote",
        result: {
          schema_version: "1.0",
          provider_name: "remote_vision",
          model_name: "dinov2-any-defect",
          dataset_version: "kaputt-manifest-v1",
          threshold_version: "frozen-e3-v1",
          detections: [],
          image_assessment: baseAssessment,
        },
      },
    ]);

    expect(results).toHaveLength(2);
    expect(results[0]?.qualification).toBe("SYNTHETIC_MOCK");
    expect(results[1]?.qualification).toBe("REMOTE_UNQUALIFIED");
    expect(results.every((item) => item.isExactE3Identity === false)).toBe(true);
    expect(describeVisionQualification(results[0]!.qualification)).toBe("합성 Mock · 연결 검증 전용");
    expect(describeVisionQualification(results[1]!.qualification)).toBe("원격 추론 · 제품 적격성 미확인");
  });

  it("keeps a below-threshold score distinct from a normal classification", () => {
    const result = readBinaryVisionAssessment([{
      result: {
        schema_version: "1.0",
        detections: [],
        image_assessment: {
          assessment_type: "ANY_DEFECT",
          model_output_name: "defect",
          score: 0.41,
          threshold: 0.8984375,
          threshold_operator: "GREATER_THAN_OR_EQUAL",
          outcome: "BELOW_HIGH_CONFIDENCE_THRESHOLD",
        },
      },
    }]);

    expect(result?.isCandidate).toBe(false);
    expect(result?.outcome).toBe("BELOW_HIGH_CONFIDENCE_THRESHOLD");
  });

  it("fails closed when score and outcome disagree", () => {
    expect(readBinaryVisionAssessment([{
      result: {
        schema_version: "1.0",
        detections: [],
        image_assessment: {
          assessment_type: "ANY_DEFECT",
          model_output_name: "defect",
          score: 0.4,
          threshold: 0.9,
          threshold_operator: "GREATER_THAN_OR_EQUAL",
          outcome: "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
        },
      },
    }])).toBeNull();
  });

  it("labels only the exact pinned remote contract as E3 identity", () => {
    const result = readBinaryVisionAssessment([{
      result: {
        schema_version: "1.0",
        provider_name: "remote_vision",
        model_name: "csight-dinov2-vits14-kaputt-binary",
        model_version: "e3-epoch10-20260827",
        model_revision: "49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e",
        taxonomy_version: "csight-any-defect-assessment-v1",
        threshold_version: "1.0",
        preprocess_version: "1.0",
        postprocess_version: "sigmoid-any-defect-v1",
        detections: [],
        image_assessment: {
          assessment_type: "ANY_DEFECT",
          model_output_name: "defect",
          score: 0.94,
          threshold: 0.8984375,
          threshold_operator: "GREATER_THAN_OR_EQUAL",
          outcome: "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
        },
      },
    }]);

    expect(result?.isExactE3Identity).toBe(true);
  });

  it("fails closed when an image-level assessment coexists with localized detections", () => {
    expect(readBinaryVisionAssessment([{
      result: {
        schema_version: "1.0",
        detections: [{ label: "CRACK", confidence: 0.99 }],
        image_assessment: {
          assessment_type: "ANY_DEFECT",
          model_output_name: "defect",
          score: 0.94,
          threshold: 0.8984375,
          threshold_operator: "GREATER_THAN_OR_EQUAL",
          outcome: "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
        },
      },
    }])).toBeNull();
  });

  it("fails closed when the public binary assessment contract markers are missing", () => {
    expect(readBinaryVisionAssessment([{
      result: {
        schema_version: "1.0",
        detections: [],
        image_assessment: {
          assessment_type: "ANY_DEFECT",
          score: 0.94,
          threshold: 0.8984375,
          outcome: "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
        },
      },
    }])).toBeNull();
  });
});
