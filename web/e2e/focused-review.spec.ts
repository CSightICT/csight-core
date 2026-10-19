import { expect, test } from "@playwright/test";
import { installApi, login, navigateInSession } from "./fixtures/api";

for (const width of [1440, 375]) {
  test(`focused review keeps detail collapsed and confirmation explicit at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 });
    await installApi(page, "validated");
    await page.route("**/*", async (route) => {
      if (/\/evidence\/[^/]+\/content$/.test(route.request().url())) return route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAoAAAAHgCAIAAAC6s0uzAAAHZElEQVR4nO3VQQ0AIBDAsJODNzygHRfsQZMK2G+zzgYAHpu8AAA+ZMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgIABA0DAgAEgYMAAEDBgAAgYMAAEDBgAAgYMAAEDBoCAAQNAwIABIGDAABAwYAAIGDAABAwYAAIGDAABAwaAgAEDQMCAASBgwAAQMGAACBgwAAQMGAACBgwAAQMGgMAFMIv68gwHKgIAAAAASUVORK5CYII=", "base64") });
      return route.fallback();
    });
    await login(page);
    await navigateInSession(page, "/reviews/task-validated");
    await expect(page.getByLabel("빠른 검토 threshold 70%")).toBeVisible();
    await expect(page.locator(".quick-review-meter")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "문의 내용 요약" })).toBeVisible();
    await expect(page.getByText("정책 근거·분석 상세 보기").locator("..")).not.toHaveAttribute("open", "");
    await expect(page.getByRole("heading", { name: "적절하다고 본 정책 근거" })).not.toBeVisible();
    await expect(page.locator(".review-product-caption")).not.toBeVisible();
    await expect(page.getByText("고객 정보", { exact: true }).locator("..")).not.toHaveAttribute("open", "");
    await page.getByText("상품·주문 정보", { exact: true }).click();
    await expect(page.locator(".review-product-caption")).toContainText("상품코드");
    await page.getByText("상품·주문 정보", { exact: true }).click();
    await expect(page.locator(".review-body img")).toBeVisible();
    const photoCenter = await page.locator(".review-body img").evaluate((img) => {
      const picture = img.getBoundingClientRect();
      const grid = img.closest(".evidence-grid")!.getBoundingClientRect();
      return Math.abs(picture.x + picture.width / 2 - grid.x - grid.width / 2);
    });
    expect(photoCenter).toBeLessThan(2);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `../output/ui-mentoring-20260911/review-${width}.png`, fullPage: true });
    await page.getByRole("button", { name: /수리 허용/ }).click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await page.getByRole("button", { name: "취소", exact: true }).click();
    await expect(page.getByRole("alertdialog")).not.toBeVisible();
    await expect(page).toHaveURL(/reviews\/task-validated$/);
  });
}


test("ready case opens decision directly and workflow details remain reachable", async ({ page }) => {
  await installApi(page, "validated");
  await login(page);
  await navigateInSession(page, "/cases/case-validated");
  await expect(page).toHaveURL(/reviews\/task-validated$/);
  await expect(page.getByRole("button", { name: /수리 허용/ })).toBeVisible();
  await page.getByText("정책 근거·분석 상세 보기", { exact: true }).click();
  await page.getByRole("link", { name: "문의 처리 단계 보기" }).click();
  await expect(page).toHaveURL(/details=1/);
  await expect(page.getByTestId("review-workbench")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "이상 후보 점수" })).toHaveCount(0);
  const photo = await page.locator(".evidence-preview").boundingBox();
  const inquiry = await page.locator(".customer-message").boundingBox();
  expect(photo && inquiry && photo.y + photo.height <= inquiry.y).toBeTruthy();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../output/ui-mentoring-20260911/workspace-photo-first.png", fullPage: true });
  await expect(page.getByText("고객·상품·주문 정보").locator("..")).not.toHaveAttribute("open", "");
  await expect(page.getByText("고정된 정책 근거 보기").locator("..")).not.toHaveAttribute("open", "");
});
