export const POC_PRODUCT_CLASSES = [
  { code: "PERSONAL_CARE_CONTAINER", label: "뷰티·개인관리 용기" },
  { code: "FOOD_OR_SUPPLEMENT_CONTAINER", label: "식품·건강보조제 용기" },
  { code: "HOUSEHOLD_CHEMICAL_CONTAINER", label: "생활화학·접착제 용기" },
  { code: "KITCHEN_OR_STORAGE_ITEM", label: "주방·수납용 경질 플라스틱" },
] as const;

export const POC_DEFECT_GROUPS = [
  { code: "OPENED_OR_DISASSEMBLED", label: "개봉·분해 상태" },
  { code: "SHAPE_OR_STRUCTURAL_DAMAGE", label: "변형·파손" },
  { code: "SURFACE_DAMAGE_OR_LEAKAGE", label: "표면 손상·누액" },
] as const;

type ProductClassCode = typeof POC_PRODUCT_CLASSES[number]["code"];
type DefectGroupCode = typeof POC_DEFECT_GROUPS[number]["code"];

export type PocClosedSetScenario = {
  productClass: ProductClassCode;
  productClassLabel: string;
  defectGroups: readonly DefectGroupCode[];
  defectGroupLabels: readonly string[];
  admissionLabel: "결함 확인 대상" | "사람 확인 저점수 참고";
  admissionDescription: string;
};

const personalCare = "뷰티·개인관리 용기";
const food = "식품·건강보조제 용기";
const chemical = "생활화학·접착제 용기";
const storage = "주방·수납용 경질 플라스틱";
const opened = "개봉·분해 상태";
const shape = "변형·파손";
const surface = "표면 손상·누액";

const defectAdmission = "사람이 상품군·원천 라벨을 승인했고 E3 점수 0.95 이상인 선별 표본";
const referenceAdmission = "사람이 참고 표본으로 승인했고 E3 점수 0.10 이하인 표본 · 정상 자동 판정 아님";

const closedSetByProductRef = new Map<string, PocClosedSetScenario>([
  ["DEMO-V2-SPRAY-CONTAINER-01", { productClass: "PERSONAL_CARE_CONTAINER", productClassLabel: personalCare, defectGroups: ["OPENED_OR_DISASSEMBLED"], defectGroupLabels: [opened], admissionLabel: "결함 확인 대상", admissionDescription: defectAdmission }],
  ["DEMO-V2-FLIPTOP-CONTAINER-02", { productClass: "PERSONAL_CARE_CONTAINER", productClassLabel: personalCare, defectGroups: ["OPENED_OR_DISASSEMBLED", "SURFACE_DAMAGE_OR_LEAKAGE"], defectGroupLabels: [opened, surface], admissionLabel: "결함 확인 대상", admissionDescription: defectAdmission }],
  ["DEMO-V2-SPRAY-CONTAINER-03", { productClass: "PERSONAL_CARE_CONTAINER", productClassLabel: personalCare, defectGroups: ["OPENED_OR_DISASSEMBLED"], defectGroupLabels: [opened], admissionLabel: "결함 확인 대상", admissionDescription: defectAdmission }],
  ["DEMO-V2-SMALL-PUMP-CONTAINER-04", { productClass: "PERSONAL_CARE_CONTAINER", productClassLabel: personalCare, defectGroups: ["OPENED_OR_DISASSEMBLED"], defectGroupLabels: [opened], admissionLabel: "결함 확인 대상", admissionDescription: defectAdmission }],
  ["DEMO-V2-SPRAY-CONTAINER-05", { productClass: "PERSONAL_CARE_CONTAINER", productClassLabel: personalCare, defectGroups: ["OPENED_OR_DISASSEMBLED"], defectGroupLabels: [opened], admissionLabel: "결함 확인 대상", admissionDescription: defectAdmission }],
  ["DEMO-V2-NOZZLE-CONTAINER-06", { productClass: "PERSONAL_CARE_CONTAINER", productClassLabel: personalCare, defectGroups: ["OPENED_OR_DISASSEMBLED", "SHAPE_OR_STRUCTURAL_DAMAGE"], defectGroupLabels: [opened, shape], admissionLabel: "결함 확인 대상", admissionDescription: defectAdmission }],
  ["DEMO-V2-PACKED-SMALL-GOODS-07", { productClass: "KITCHEN_OR_STORAGE_ITEM", productClassLabel: storage, defectGroups: [], defectGroupLabels: [], admissionLabel: "사람 확인 저점수 참고", admissionDescription: referenceAdmission }],
  ["DEMO-V2-PACKED-CYLINDER-GOODS-08", { productClass: "KITCHEN_OR_STORAGE_ITEM", productClassLabel: storage, defectGroups: [], defectGroupLabels: [], admissionLabel: "사람 확인 저점수 참고", admissionDescription: referenceAdmission }],
  ["DEMO-V2-PACKED-HOUSEHOLD-SET-09", { productClass: "KITCHEN_OR_STORAGE_ITEM", productClassLabel: storage, defectGroups: [], defectGroupLabels: [], admissionLabel: "사람 확인 저점수 참고", admissionDescription: referenceAdmission }],
  ["DEMO-V2-PACKED-RECTANGLE-GOODS-10", { productClass: "KITCHEN_OR_STORAGE_ITEM", productClassLabel: storage, defectGroups: [], defectGroupLabels: [], admissionLabel: "사람 확인 저점수 참고", admissionDescription: referenceAdmission }],
  ["DEMO-V3-CONFECTIONERY-CONTAINER-11", { productClass: "FOOD_OR_SUPPLEMENT_CONTAINER", productClassLabel: food, defectGroups: ["OPENED_OR_DISASSEMBLED", "SHAPE_OR_STRUCTURAL_DAMAGE"], defectGroupLabels: [opened, shape], admissionLabel: "결함 확인 대상", admissionDescription: defectAdmission }],
  ["DEMO-V3-ADHESIVE-TUBE-12", { productClass: "HOUSEHOLD_CHEMICAL_CONTAINER", productClassLabel: chemical, defectGroups: ["OPENED_OR_DISASSEMBLED"], defectGroupLabels: [opened], admissionLabel: "결함 확인 대상", admissionDescription: defectAdmission }],
  ["DEMO-V3-HANDCREAM-TUBE-13", { productClass: "PERSONAL_CARE_CONTAINER", productClassLabel: personalCare, defectGroups: ["OPENED_OR_DISASSEMBLED"], defectGroupLabels: [opened], admissionLabel: "결함 확인 대상", admissionDescription: defectAdmission }],
  ["DEMO-V3-WATER-TREATMENT-14", { productClass: "HOUSEHOLD_CHEMICAL_CONTAINER", productClassLabel: chemical, defectGroups: ["OPENED_OR_DISASSEMBLED"], defectGroupLabels: [opened], admissionLabel: "결함 확인 대상", admissionDescription: defectAdmission }],
  ["DEMO-V3-MUFFIN-TRAY-15", { productClass: "KITCHEN_OR_STORAGE_ITEM", productClassLabel: storage, defectGroups: ["OPENED_OR_DISASSEMBLED"], defectGroupLabels: [opened], admissionLabel: "결함 확인 대상", admissionDescription: defectAdmission }],
  ["DEMO-V3-CLEANER-CONTAINER-16", { productClass: "HOUSEHOLD_CHEMICAL_CONTAINER", productClassLabel: chemical, defectGroups: ["OPENED_OR_DISASSEMBLED"], defectGroupLabels: [opened], admissionLabel: "결함 확인 대상", admissionDescription: defectAdmission }],
  ["DEMO-V3-PACKED-CABLE-17", { productClass: "KITCHEN_OR_STORAGE_ITEM", productClassLabel: storage, defectGroups: [], defectGroupLabels: [], admissionLabel: "사람 확인 저점수 참고", admissionDescription: referenceAdmission }],
  ["DEMO-V3-PACKED-ROLL-18", { productClass: "KITCHEN_OR_STORAGE_ITEM", productClassLabel: storage, defectGroups: [], defectGroupLabels: [], admissionLabel: "사람 확인 저점수 참고", admissionDescription: referenceAdmission }],
  ["DEMO-V3-PACKED-TRAY-19", { productClass: "KITCHEN_OR_STORAGE_ITEM", productClassLabel: storage, defectGroups: [], defectGroupLabels: [], admissionLabel: "사람 확인 저점수 참고", admissionDescription: referenceAdmission }],
  ["DEMO-V3-PACKED-BOARD-20", { productClass: "KITCHEN_OR_STORAGE_ITEM", productClassLabel: storage, defectGroups: [], defectGroupLabels: [], admissionLabel: "사람 확인 저점수 참고", admissionDescription: referenceAdmission }],
]);

export function demoPocClosedSet(productRef: string): PocClosedSetScenario | undefined {
  return closedSetByProductRef.get(productRef);
}
