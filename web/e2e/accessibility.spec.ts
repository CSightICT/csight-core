import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { installApi, login, navigateInSession } from "./fixtures/api";

const viewports = [320, 375, 768, 1024, 1440] as const;

async function expectReleaseAccessibility(page: Page, label: string) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"])
    .analyze();
  const severe = results.violations
    .filter(({ impact }) => impact === "serious" || impact === "critical")
    .map(({ id, impact, nodes }) => ({
      id,
      impact,
      nodes: nodes.map(({ target, failureSummary, html }) => ({ target, failureSummary, html })),
    }));
  expect(severe, `${label}: serious/critical axe violations`).toEqual([]);

  const overflow = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    body: document.body.scrollWidth - document.body.clientWidth,
  }));
  expect(overflow.document, `${label}: document horizontal overflow`).toBeLessThanOrEqual(0);
  expect(overflow.body, `${label}: body horizontal overflow`).toBeLessThanOrEqual(0);

  const undersizedTargets = await page.locator(
    "button:visible, a[href]:visible, input:visible, select:visible, textarea:visible, [role='button']:visible",
  ).evaluateAll((elements) => elements.flatMap((element) => {
    const rectangle = element.getBoundingClientRect();
    if (rectangle.width >= 44 && rectangle.height >= 44) return [];
    return [{
      element: element.tagName.toLowerCase(),
      name: element.getAttribute("aria-label") ?? element.textContent?.trim().slice(0, 80) ?? "",
      width: Math.round(rectangle.width),
      height: Math.round(rectangle.height),
    }];
  }));
  expect(undersizedTargets, `${label}: interactive targets smaller than 44x44px`).toEqual([]);
}

async function expectQueueControlsAligned(page: Page, sortLabel: string) {
  const heights = await Promise.all([
    page.getByPlaceholder("주문·상품·문의 번호 검색").evaluate((element) => element.closest("label")?.getBoundingClientRect().height ?? 0),
    page.getByLabel(sortLabel).evaluate((element) => element.closest("label")?.getBoundingClientRect().height ?? 0),
  ]);
  expect(heights).toEqual([48, 48]);
}

for (const width of viewports) {
  test.describe(`${width}px release accessibility`, () => {
    test.use({ viewport: { width, height: 900 }, reducedMotion: "reduce" });

    test("operator routes have no severe accessibility or horizontal-overflow failures", async ({ page }) => {
      await installApi(page, "validated");
      await login(page);

      await expect(page).toHaveTitle(/상담 케이스/);
      await expect(page.getByRole("link", { name: "새 케이스" })).toHaveCount(0);
      await expectQueueControlsAligned(page, "문의 정렬");
      await expectReleaseAccessibility(page, `${width}px cases`);

      await navigateInSession(page, "/reviews");
      await expect(page).toHaveTitle(/검토/);
      await expectQueueControlsAligned(page, "검토 정렬");
      await expectReleaseAccessibility(page, `${width}px reviews`);

      await navigateInSession(page, "/reviews/task-validated");
      const quickDecision = page.getByRole("button", { name: /수리 허용/ });
      await expect(quickDecision).toBeVisible();
      await expectReleaseAccessibility(page, `${width}px review detail`);

      await quickDecision.click();
      const confirmation = page.getByRole("alertdialog", { name: /수리 승인/ });
      await expect(confirmation).toBeVisible();
      await expectReleaseAccessibility(page, `${width}px confirmation`);

      await page.keyboard.press("Escape");
      await expect(confirmation).toBeHidden();
      await expect(quickDecision).toBeFocused();

      await navigateInSession(page, "/cases/case-validated");
      await expect(page).toHaveTitle(/케이스 업무 공간/);
      await expectReleaseAccessibility(page, `${width}px case workspace`);
    });
  });
}
