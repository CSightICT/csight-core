import { describe, expect, it } from "vitest";

import { demoProductDisplayName } from "./productScenarioCatalog";

describe("demoProductDisplayName", () => {
  it("labels current, legacy, and internal PoC product references with Korean product names", () => {
    const currentDatabaseProductRefs = [
      "DEMO-ACRYLIC-ORGANIZER-07",
      "DEMO-COMPACT-CASE-10",
      "DEMO-CYLINDER-CASE-08",
      "DEMO-DISPENSER-03",
      "DEMO-LOTION-PUMP-02",
      "DEMO-MIST-PUMP-05",
      "DEMO-PUMP-BOTTLE-01",
      "DEMO-SANITIZER-PUMP-06",
      "DEMO-STORAGE-SET-09",
      "DEMO-TRAVEL-PUMP-04",
      "DEMO-V2-ACRYLIC-ORGANIZER-07",
      "DEMO-V2-COMPACT-CASE-10",
      "DEMO-V2-CYLINDER-CASE-08",
      "DEMO-V2-DISPENSER-03",
      "DEMO-V2-FLIPTOP-CONTAINER-02",
      "DEMO-V2-LOTION-PUMP-02",
      "DEMO-V2-MIST-PUMP-05",
      "DEMO-V2-NOZZLE-CONTAINER-06",
      "DEMO-V2-PACKED-CYLINDER-GOODS-08",
      "DEMO-V2-PACKED-HOUSEHOLD-SET-09",
      "DEMO-V2-PACKED-RECTANGLE-GOODS-10",
      "DEMO-V2-PACKED-SMALL-GOODS-07",
      "DEMO-V2-PUMP-BOTTLE-01",
      "DEMO-V2-SANITIZER-PUMP-06",
      "DEMO-V2-SMALL-PUMP-CONTAINER-04",
      "DEMO-V2-SPRAY-CONTAINER-01",
      "DEMO-V2-SPRAY-CONTAINER-03",
      "DEMO-V2-SPRAY-CONTAINER-05",
      "DEMO-V2-STORAGE-SET-09",
      "DEMO-V2-TRAVEL-PUMP-04",
      "DEMO-V3-ADHESIVE-TUBE-12",
      "DEMO-V3-CLEANER-CONTAINER-16",
      "DEMO-V3-CONFECTIONERY-CONTAINER-11",
      "DEMO-V3-HANDCREAM-TUBE-13",
      "DEMO-V3-MUFFIN-TRAY-15",
      "DEMO-V3-PACKED-BOARD-20",
      "DEMO-V3-PACKED-CABLE-17",
      "DEMO-V3-PACKED-ROLL-18",
      "DEMO-V3-PACKED-TRAY-19",
      "DEMO-V3-WATER-TREATMENT-14",
      "KAPUTT-PLASTIC-HARD-PROXY",
      "LOCAL-MLX-SYNTHETIC",
      "POLICY-SMOKE-HIGH-VALUE",
      "QB-P-11d313fe",
      "QUERY-SMOKE-PRODUCT-ed6000c488ac46a395d602b665b7d53b",
      "SKU-A-1",
      "SKU-A-2",
      "SKU-B-1",
      "SYN-HDP-100",
    ];

    expect(currentDatabaseProductRefs.filter((productRef) => !demoProductDisplayName(productRef))).toEqual([]);
    expect(demoProductDisplayName("DEMO-COMPACT-CASE-10")).toBe("플랫케이스 오거나이저 2P");
    expect(demoProductDisplayName("POLICY-SMOKE-HIGH-VALUE")).toBe("프리미엄 스택 수납함 5L");
  });
});
