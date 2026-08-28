import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DemoProvenance, readDemoImageObservation, readDemoProvenance } from "./DemoProvenance";

const valid = {
    schema_version: "1.0",
  dataset_id: "realistic-internal-demo-v1",
  scenario_scope: "INTERNAL_CURATED_6_DEFECT_4_BELOW_THRESHOLD",
  source_grade: "KAPUTT_SELECTED_CORRECT_POSITIVE",
  selection_bias: "POSITIVE_ONLY_CORRECT_ONLY_HIGH_CONFIDENCE",
  rights_status: "INTERNAL_RESTRICTED_PROVENANCE_UNVERIFIED",
  policy_input_linkage: "NOT_LINKED_TO_POLICY_INPUT",
  source_rank: 54,
  source_image_sha256: "f249bf013a12603ee0810df8c2a573cc82518a916da874de0fe13ee6048bb675",
  source_capture_id: "1b9c77de-4f12-4005-a4da-1d1b85d68025",
};

describe("internal demo provenance", () => {
  it("renders the approved human-readable boundaries without raw SHA or UUID", () => {
    render(<DemoProvenance attributes={{ realistic_demo: valid }} />);

    expect(screen.getByText("선별 이미지 문의 v1")).toBeVisible();
    expect(screen.getByText("선별 데이터")).toBeVisible();
    expect(screen.getByText("재사용 권리 미확인")).toBeVisible();
    expect(screen.getByText("Vision은 정책 판단 입력과 연결되지 않음")).toBeVisible();
    expect(screen.getByText(/Kaputt 선별 정답 양성 표본/)).toBeVisible();
    expect(document.body).not.toHaveTextContent(valid.source_image_sha256);
    expect(document.body).not.toHaveTextContent(valid.source_capture_id);
    expect(document.body).not.toHaveTextContent(valid.selection_bias);
  });

  it("supports curated_demo as a compatibility alias with the same strict contract", () => {
    expect(readDemoProvenance({ curated_demo: { ...valid, source_grade: "USER_SUPPLIED_NORMAL_REFERENCE" } })).toMatchObject({
      status: "VALID",
      sourceLabel: "사용자 제공 정상 참조 표본",
    });
  });

  it("renders the explicit fictional ecommerce v2 scope with the same safety boundaries", () => {
    const attributes = { realistic_demo: {
      ...valid,
      schema_version: "2.0",
      dataset_id: "realistic-internal-demo-v2",
      scenario_scope: "INTERNAL_CURATED_ECOMMERCE_INQUIRY_6_DEFECT_4_BELOW_THRESHOLD",
      narrative_revision: "VISUAL_ALIGNED_R1",
    },
    demo_image_observation: "뚜껑 결합부의 균열과 가장자리 파손이 보입니다.",
    demo_claim_boundary: "CUSTOMER_STATEMENT_ONLY_FOR_NON_VISIBLE_FACTS",
    };
    render(<DemoProvenance attributes={attributes} />);

    expect(screen.getByText("이커머스 상품 문의 v2")).toBeVisible();
    expect(screen.getByText("재사용 권리 미확인")).toBeVisible();
    expect(screen.getByText("Vision은 정책 판단 입력과 연결되지 않음")).toBeVisible();
    expect(readDemoProvenance(attributes)?.schemaVersion).toBe("2.0");
    expect(readDemoImageObservation(attributes)).toBe("뚜껑 결합부의 균열과 가장자리 파손이 보입니다.");
  });

  it("accepts the commerce-context R2 revision without weakening provenance checks", () => {
    const provenance = readDemoProvenance({ realistic_demo: {
      ...valid,
      schema_version: "2.0",
      dataset_id: "realistic-internal-demo-v2",
      scenario_scope: "INTERNAL_CURATED_ECOMMERCE_INQUIRY_6_DEFECT_4_BELOW_THRESHOLD",
      narrative_revision: "COMMERCE_CONTEXT_R2",
    } });

    expect(provenance).toMatchObject({ status: "VALID", schemaVersion: "2.0" });
  });

  it("accepts the twenty-case expansion contract and image observation boundary", () => {
    const attributes = {
      realistic_demo: {
        ...valid,
        schema_version: "3.0",
        dataset_id: "realistic-internal-demo-v3",
        scenario_scope: "INTERNAL_CURATED_ECOMMERCE_EXPANSION_12_DEFECT_8_REFERENCE_TOTAL",
        narrative_revision: "CLOSED_SET_EXPANSION_R3",
      },
      demo_image_observation: "튜브형 용기와 마개가 떨어져 보입니다.",
      demo_claim_boundary: "CUSTOMER_STATEMENT_ONLY_FOR_NON_VISIBLE_FACTS",
    };

    expect(readDemoProvenance(attributes)).toMatchObject({
      status: "VALID",
      schemaVersion: "3.0",
      scenarioLabel: "이커머스 상품 문의 확장 v3",
    });
    expect(readDemoImageObservation(attributes)).toBe("튜브형 용기와 마개가 떨어져 보입니다.");
  });

  it("fails closed when the image observation boundary is absent or malformed", () => {
    const v2 = {
      realistic_demo: {
        ...valid,
        schema_version: "2.0",
        dataset_id: "realistic-internal-demo-v2",
        scenario_scope: "INTERNAL_CURATED_ECOMMERCE_INQUIRY_6_DEFECT_4_BELOW_THRESHOLD",
        narrative_revision: "VISUAL_ALIGNED_R1",
      },
      demo_image_observation: "외관 일부가 보입니다.",
    };

    expect(readDemoImageObservation(v2)).toBeNull();
    expect(readDemoImageObservation({
      ...v2,
      demo_claim_boundary: "VISION_CONFIRMS_CUSTOMER_STATEMENT",
    })).toBeNull();
  });

  it("fails closed without reflecting unexpected provenance values", () => {
    const unexpected = "UNEXPECTED-SECRET-LIKE-VALUE";
    render(<DemoProvenance attributes={{ realistic_demo: { ...valid, rights_status: unexpected } }} />);

    expect(screen.getByTestId("demo-provenance-unknown")).toHaveTextContent("데이터 출처 상태 확인 필요");
    expect(document.body).not.toHaveTextContent(unexpected);
    expect(document.body).not.toHaveTextContent("Vision은 정책 판단 입력과 연결되지 않음");
  });
});
