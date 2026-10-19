import { expect, test } from "@playwright/test";
import { installApi, login, navigateInSession } from "./fixtures/api";

for (const width of [1440, 375]) {
  test(`data assets distinguish saved and eligible records at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 });
    await installApi(page, "validated");
    await page.route("**/api/v1/data-assets/summary", (route) => route.fulfill({ json: {
      schema_version: "1.0.0", generated_at: "2026-09-20T00:00:00Z", total_records: 12,
      eligible_records: 0, excluded_records: 12, eligible_source_scope: "PILOT_LIVE",
      source_scope_distribution: { SYNTHETIC: 12 }, baseline_minimum: 30, drift_review_minimum: 60,
      readiness_status: "COLLECTING_BASELINE", drift_evaluation_available: false,
      decision_distribution: {}, resolution_distribution: {}, product_distribution: {},
      model_version_distribution: {}, policy_version_distribution: {}, recent_records: [],
    } }));
    await login(page, "admin@demo.test");
    await navigateInSession(page, "/data-assets");
    await expect(page.getByText("쌓인 처리 기록").locator("..")).toContainText("12건");
    await expect(page.getByText("실제 운영 분석에 쓸 수 있는 기록").locator("..")).toContainText("0건");
    await expect(page.getByText("아직 표시할 실운영 사례가 없습니다")).toBeVisible();
    await expect(page.getByRole("heading", { name: "분석 모델 버전" })).not.toBeVisible();
    await page.screenshot({ path: `../output/data-assets-${width}.png`, fullPage: true });
    await page.getByText("처리 현황과 관리 정보 자세히 보기", { exact: true }).click();
    await expect(page.getByRole("heading", { name: "분석 모델 버전" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
}
