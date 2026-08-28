export type DemoProductScenario = {
  productRef: string;
  displayName: string;
  productFamily: string;
  syntheticSku: string;
  priceBand: {
    currency: "KRW";
    min: number;
    max: number;
    representative: number;
  };
  inquiryPurpose: string;
  sourceRank: number;
  sourceKind: "SELECTED_CORRECT_DEFECT" | "BELOW_THRESHOLD_REFERENCE";
  basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH";
};

const scenarios = [
  {
    productRef: "DEMO-V2-SPRAY-CONTAINER-01",
    displayName: "루미에어 미스트 에센스 120",
    productFamily: "스프레이형 플라스틱 용기",
    syntheticSku: "CS-DEMO-SPR-001",
    priceBand: { currency: "KRW", min: 19_000, max: 29_000, representative: 24_900 },
    inquiryPurpose: "보호캡 고정 불량 의심에 따른 동일 상품 교환",
    sourceRank: 3,
    sourceKind: "SELECTED_CORRECT_DEFECT",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V2-FLIPTOP-CONTAINER-02",
    displayName: "화이트랩 바디 로션 300",
    productFamily: "플립탑 플라스틱 용기",
    syntheticSku: "CS-DEMO-FLP-002",
    priceBand: { currency: "KRW", min: 15_000, max: 25_000, representative: 18_900 },
    inquiryPurpose: "잠금·누수 고객 진술에 따른 반품 및 환불",
    sourceRank: 32,
    sourceKind: "SELECTED_CORRECT_DEFECT",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V2-SPRAY-CONTAINER-03",
    displayName: "바이올렛 리페어 에센스 100",
    productFamily: "스프레이형 플라스틱 용기",
    syntheticSku: "CS-DEMO-SPR-003",
    priceBand: { currency: "KRW", min: 21_000, max: 35_000, representative: 27_900 },
    inquiryPurpose: "분사부 부품 교체 또는 수리 가능 여부 확인",
    sourceRank: 54,
    sourceKind: "SELECTED_CORRECT_DEFECT",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V2-SMALL-PUMP-CONTAINER-04",
    displayName: "골드리프 펌프 세럼 50",
    productFamily: "펌프형 소형 플라스틱 용기",
    syntheticSku: "CS-DEMO-PMP-004",
    priceBand: { currency: "KRW", min: 24_000, max: 42_000, representative: 32_900 },
    inquiryPurpose: "보호캡 분리 상태 확인과 동일 구성 재배송",
    sourceRank: 58,
    sourceKind: "SELECTED_CORRECT_DEFECT",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V2-SPRAY-CONTAINER-05",
    displayName: "로즈핏 헤어 미스트 150",
    productFamily: "스프레이형 플라스틱 용기",
    syntheticSku: "CS-DEMO-SPR-005",
    priceBand: { currency: "KRW", min: 14_000, max: 24_000, representative: 18_900 },
    inquiryPurpose: "사용 중 튐 고객 진술에 따른 안전 반품 검토",
    sourceRank: 78,
    sourceKind: "SELECTED_CORRECT_DEFECT",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V2-NOZZLE-CONTAINER-06",
    displayName: "듀얼캡 리필 디스펜서 400",
    productFamily: "노즐형 리필 플라스틱 용기",
    syntheticSku: "CS-DEMO-NOZ-006",
    priceBand: { currency: "KRW", min: 8_000, max: 15_000, representative: 11_900 },
    inquiryPurpose: "조립 방법과 구성 부품 누락 여부 확인",
    sourceRank: 80,
    sourceKind: "SELECTED_CORRECT_DEFECT",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V2-PACKED-SMALL-GOODS-07",
    displayName: "모듈박스 미니 수납함 3단",
    productFamily: "포장된 소형 수납용품",
    syntheticSku: "CS-DEMO-PKG-007",
    priceBand: { currency: "KRW", min: 16_000, max: 25_000, representative: 19_900 },
    inquiryPurpose: "포장 미개봉 상태의 옵션 불일치 교환",
    sourceRank: 2,
    sourceKind: "BELOW_THRESHOLD_REFERENCE",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V2-PACKED-CYLINDER-GOODS-08",
    displayName: "롱스택 원통 수납통 1L",
    productFamily: "포장된 원통형 수납용품",
    syntheticSku: "CS-DEMO-CYL-008",
    priceBand: { currency: "KRW", min: 14_000, max: 23_000, representative: 17_900 },
    inquiryPurpose: "미사용 단순 변심 반품과 배송비 기준 문의",
    sourceRank: 8,
    sourceKind: "BELOW_THRESHOLD_REFERENCE",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V2-PACKED-HOUSEHOLD-SET-09",
    displayName: "멀티홈 욕실 정리세트 4P",
    productFamily: "포장된 생활 수납용품 세트",
    syntheticSku: "CS-DEMO-SET-009",
    priceBand: { currency: "KRW", min: 18_000, max: 32_000, representative: 24_900 },
    inquiryPurpose: "주문 수량 누락 고객 진술에 따른 재배송 문의",
    sourceRank: 17,
    sourceKind: "BELOW_THRESHOLD_REFERENCE",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V2-PACKED-RECTANGLE-GOODS-10",
    displayName: "플랫케이스 오거나이저 2P",
    productFamily: "포장된 직사각형 수납용품",
    syntheticSku: "CS-DEMO-REC-010",
    priceBand: { currency: "KRW", min: 15_000, max: 27_000, representative: 21_900 },
    inquiryPurpose: "색상 차이 고객 진술에 따른 단순 변심 환불",
    sourceRank: 23,
    sourceKind: "BELOW_THRESHOLD_REFERENCE",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V3-CONFECTIONERY-CONTAINER-11",
    displayName: "스위트믹스 파티 캔디 컨테이너 1kg",
    productFamily: "식품 보관용 경질 플라스틱 용기",
    syntheticSku: "CS-DEMO-FOD-011",
    priceBand: { currency: "KRW", min: 17_000, max: 27_000, representative: 21_900 },
    inquiryPurpose: "배송 중 용기 결합부 이탈 가능성에 따른 교환",
    sourceRank: 1,
    sourceKind: "SELECTED_CORRECT_DEFECT",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V3-ADHESIVE-TUBE-12",
    displayName: "픽스온 정밀 접착제 50",
    productFamily: "튜브형 생활화학 용기",
    syntheticSku: "CS-DEMO-CHM-012",
    priceBand: { currency: "KRW", min: 9_000, max: 18_000, representative: 12_900 },
    inquiryPurpose: "마개 분리와 밀봉 불확실성에 따른 안전 환불",
    sourceRank: 9,
    sourceKind: "SELECTED_CORRECT_DEFECT",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V3-HANDCREAM-TUBE-13",
    displayName: "프레시가든 핸드크림 80",
    productFamily: "튜브형 개인관리 용기",
    syntheticSku: "CS-DEMO-PCS-013",
    priceBand: { currency: "KRW", min: 12_000, max: 23_000, representative: 16_900 },
    inquiryPurpose: "분리된 마개·입구 부품 수리 가능 여부 확인",
    sourceRank: 22,
    sourceKind: "SELECTED_CORRECT_DEFECT",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V3-WATER-TREATMENT-14",
    displayName: "아쿠아케어 수질관리제 250",
    productFamily: "생활화학 액상 제품 용기",
    syntheticSku: "CS-DEMO-CHM-014",
    priceBand: { currency: "KRW", min: 14_000, max: 25_000, representative: 18_900 },
    inquiryPurpose: "주입구 부품 이탈·누락 가능성에 따른 재배송",
    sourceRank: 31,
    sourceKind: "SELECTED_CORRECT_DEFECT",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V3-MUFFIN-TRAY-15",
    displayName: "홈베이크 미니 머핀팬 24구",
    productFamily: "주방용 경질 플라스틱 트레이",
    syntheticSku: "CS-DEMO-KIT-015",
    priceBand: { currency: "KRW", min: 19_000, max: 32_000, representative: 24_900 },
    inquiryPurpose: "덮개와 본체 결합 상태 불확실성에 따른 반품",
    sourceRank: 73,
    sourceKind: "SELECTED_CORRECT_DEFECT",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V3-CLEANER-CONTAINER-16",
    displayName: "클린탭 배수구 세정제 300",
    productFamily: "생활화학 세정제 용기",
    syntheticSku: "CS-DEMO-CHM-016",
    priceBand: { currency: "KRW", min: 10_000, max: 21_000, representative: 14_900 },
    inquiryPurpose: "마개 분리 상태와 추가 촬영 위치 안내",
    sourceRank: 79,
    sourceKind: "SELECTED_CORRECT_DEFECT",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V3-PACKED-CABLE-17",
    displayName: "케이블큐브 미니 정리함 L",
    productFamily: "포장된 소형 수납용품",
    syntheticSku: "CS-DEMO-STO-017",
    priceBand: { currency: "KRW", min: 10_000, max: 20_000, representative: 13_900 },
    inquiryPurpose: "포장 표기와 주문 옵션 불일치 가능성에 따른 교환",
    sourceRank: 1,
    sourceKind: "BELOW_THRESHOLD_REFERENCE",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V3-PACKED-ROLL-18",
    displayName: "슬림롤 주방 보관 케이스 45",
    productFamily: "포장된 주방 수납용품",
    syntheticSku: "CS-DEMO-KIT-018",
    priceBand: { currency: "KRW", min: 13_000, max: 24_000, representative: 17_900 },
    inquiryPurpose: "미사용 단순 변심 반품 조건 확인",
    sourceRank: 20,
    sourceKind: "BELOW_THRESHOLD_REFERENCE",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V3-PACKED-TRAY-19",
    displayName: "클리어스택 욕실 수납 트레이 2P",
    productFamily: "포장된 직사각 수납용품",
    syntheticSku: "CS-DEMO-STO-019",
    priceBand: { currency: "KRW", min: 15_000, max: 27_000, representative: 19_900 },
    inquiryPurpose: "포장 상태에서 수량 누락 가능성에 따른 재배송",
    sourceRank: 65,
    sourceKind: "BELOW_THRESHOLD_REFERENCE",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
  {
    productRef: "DEMO-V3-PACKED-BOARD-20",
    displayName: "내추럴그립 논슬립 도마 M",
    productFamily: "포장된 주방용 경질 플라스틱",
    syntheticSku: "CS-DEMO-KIT-020",
    priceBand: { currency: "KRW", min: 11_000, max: 22_000, representative: 15_900 },
    inquiryPurpose: "미사용 색상 차이 가능성에 따른 환불",
    sourceRank: 67,
    sourceKind: "BELOW_THRESHOLD_REFERENCE",
    basis: "SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH",
  },
] as const satisfies readonly DemoProductScenario[];

const byProductRef = new Map<string, DemoProductScenario>(
  scenarios.map((scenario) => [scenario.productRef, scenario]),
);

const legacyAliases = new Map<string, string>([
  ["DEMO-PUMP-BOTTLE-01", "DEMO-V2-SPRAY-CONTAINER-01"],
  ["DEMO-LOTION-PUMP-02", "DEMO-V2-FLIPTOP-CONTAINER-02"],
  ["DEMO-DISPENSER-03", "DEMO-V2-SPRAY-CONTAINER-03"],
  ["DEMO-TRAVEL-PUMP-04", "DEMO-V2-SMALL-PUMP-CONTAINER-04"],
  ["DEMO-MIST-PUMP-05", "DEMO-V2-SPRAY-CONTAINER-05"],
  ["DEMO-SANITIZER-PUMP-06", "DEMO-V2-NOZZLE-CONTAINER-06"],
  ["DEMO-ACRYLIC-ORGANIZER-07", "DEMO-V2-PACKED-SMALL-GOODS-07"],
  ["DEMO-CYLINDER-CASE-08", "DEMO-V2-PACKED-CYLINDER-GOODS-08"],
  ["DEMO-STORAGE-SET-09", "DEMO-V2-PACKED-HOUSEHOLD-SET-09"],
  ["DEMO-COMPACT-CASE-10", "DEMO-V2-PACKED-RECTANGLE-GOODS-10"],
  ["DEMO-V2-PUMP-BOTTLE-01", "DEMO-V2-SPRAY-CONTAINER-01"],
  ["DEMO-V2-LOTION-PUMP-02", "DEMO-V2-FLIPTOP-CONTAINER-02"],
  ["DEMO-V2-DISPENSER-03", "DEMO-V2-SPRAY-CONTAINER-03"],
  ["DEMO-V2-TRAVEL-PUMP-04", "DEMO-V2-SMALL-PUMP-CONTAINER-04"],
  ["DEMO-V2-MIST-PUMP-05", "DEMO-V2-SPRAY-CONTAINER-05"],
  ["DEMO-V2-SANITIZER-PUMP-06", "DEMO-V2-NOZZLE-CONTAINER-06"],
  ["DEMO-V2-ACRYLIC-ORGANIZER-07", "DEMO-V2-PACKED-SMALL-GOODS-07"],
  ["DEMO-V2-CYLINDER-CASE-08", "DEMO-V2-PACKED-CYLINDER-GOODS-08"],
  ["DEMO-V2-STORAGE-SET-09", "DEMO-V2-PACKED-HOUSEHOLD-SET-09"],
  ["DEMO-V2-COMPACT-CASE-10", "DEMO-V2-PACKED-RECTANGLE-GOODS-10"],
]);

const internalDemoNames = new Map<string, string>([
  ["KAPUTT-PLASTIC-HARD-PROXY", "클리어락 다용도 밀폐용기 1.2L"],
  ["LOCAL-MLX-SYNTHETIC", "데일리픽 펌프 디스펜서 300"],
  ["POLICY-SMOKE-HIGH-VALUE", "프리미엄 스택 수납함 5L"],
  ["SKU-A-1", "클리어박스 수납함 A형 1P"],
  ["SKU-A-2", "클리어박스 수납함 A형 2P"],
  ["SKU-B-1", "클리어박스 수납함 B형 1P"],
  ["SYN-HDP-100", "하드쉘 멀티 수납 케이스"],
]);

export const DEMO_PRODUCT_SCENARIOS: readonly DemoProductScenario[] = scenarios;

export function demoProductScenario(productRef: string): DemoProductScenario | undefined {
  return byProductRef.get(productRef);
}

export function demoProductDisplayName(productRef: string): string | undefined {
  const direct = byProductRef.get(productRef)?.displayName;
  if (direct) return direct;
  const alias = legacyAliases.get(productRef);
  if (alias) return byProductRef.get(alias)?.displayName;
  const internalName = internalDemoNames.get(productRef);
  if (internalName) return internalName;
  if (productRef.startsWith("QB-P-")) return "모던핏 데스크 오거나이저";
  if (productRef.startsWith("QUERY-SMOKE-PRODUCT-")) return "클리어홈 다용도 보관함 2P";
  return undefined;
}

export function formatSyntheticPriceBand(scenario: DemoProductScenario): string {
  const formatter = new Intl.NumberFormat("ko-KR");
  return `${formatter.format(scenario.priceBand.min)}~${formatter.format(scenario.priceBand.max)}원`;
}
