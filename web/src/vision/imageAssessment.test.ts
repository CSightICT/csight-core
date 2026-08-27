import { describe, expect, it } from "vitest";

import {
  formatVisionProbability,
  readBinaryVisionAssessment,
  readBinaryVisionAssessments,
} from "./imageAssessment";

describe("binary Vision assessment presentation", () => {
  it("presents a threshold candidate without inventing localization", () => {
    const result = readBinaryVisionAssessment([{
      result: {
        detections: [],
        image_assessment: {
          assessment_type: "ANY_DEFECT",
          score: 0.94,
          threshold: 0.8984375,
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
    });
    expect(formatVisionProbability(result!.threshold)).toBe("89.84%");
  });

  it("keeps every image assessment and separates Mock from remote qualification", () => {
    const baseAssessment = {
      assessment_type: "ANY_DEFECT",
      score: 0.94,
      threshold: 0.8984375,
      outcome: "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
    };
    const results = readBinaryVisionAssessments([
      {
        evidence_id: "evidence-mock",
        result: {
          provider_name: "mock",
          model_name: "contract-mock",
          dataset_version: "synthetic-any-defect-v1",
          threshold_version: "synthetic-threshold-v1",
          image_assessment: baseAssessment,
        },
      },
      {
        evidence_id: "evidence-remote",
        result: {
          provider_name: "remote_vision",
          model_name: "dinov2-any-defect",
          dataset_version: "kaputt-manifest-v1",
          threshold_version: "frozen-e3-v1",
          image_assessment: baseAssessment,
        },
      },
    ]);

    expect(results).toHaveLength(2);
    expect(results[0]?.qualification).toBe("SYNTHETIC_MOCK");
    expect(results[1]?.qualification).toBe("REMOTE_UNQUALIFIED");
  });

  it("keeps a below-threshold score distinct from a normal classification", () => {
    const result = readBinaryVisionAssessment([{
      result: {
        image_assessment: {
          assessment_type: "ANY_DEFECT",
          score: 0.41,
          threshold: 0.8984375,
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
        image_assessment: {
          assessment_type: "ANY_DEFECT",
          score: 0.4,
          threshold: 0.9,
          outcome: "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
        },
      },
    }])).toBeNull();
  });
});
