import { describe, expect, it } from "vitest";

import {
  POC_DEFECT_GROUPS,
  POC_PRODUCT_CLASSES,
  demoPocClosedSet,
} from "./pocClosedSetCatalog";
import { DEMO_PRODUCT_SCENARIOS } from "./productScenarioCatalog";

describe("PoC closed-set catalog", () => {
  it("defines four product classes and three defect groups", () => {
    expect(POC_PRODUCT_CLASSES).toHaveLength(4);
    expect(POC_DEFECT_GROUPS).toHaveLength(3);
  });

  it("assigns every curated demo image without treating references as normal", () => {
    const assigned = DEMO_PRODUCT_SCENARIOS.map((item) => demoPocClosedSet(item.productRef));

    expect(assigned.every(Boolean)).toBe(true);
    expect(assigned.filter((item) => item?.admissionLabel === "결함 확인 대상")).toHaveLength(12);
    expect(assigned.filter((item) => item?.admissionLabel === "사람 확인 저점수 참고")).toHaveLength(8);
    expect(new Set(assigned.map((item) => item?.productClass))).toEqual(new Set(POC_PRODUCT_CLASSES.map((item) => item.code)));
    for (const item of assigned.filter((candidate) => candidate?.admissionLabel === "사람 확인 저점수 참고")) {
      expect(item?.defectGroups).toEqual([]);
      expect(item?.admissionDescription).toContain("정상 자동 판정 아님");
    }
  });

  it("does not assign unknown products to the PoC", () => {
    expect(demoPocClosedSet("UNKNOWN-SKU")).toBeUndefined();
  });
});
