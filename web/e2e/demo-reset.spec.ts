import { expect, test } from "@playwright/test";
import { installApi, login, navigateInSession } from "./fixtures/api";

for (const width of [1440, 375]) {
  test(`demo reset confirmation at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 });
    await installApi(page, "validated");
    await page.route("**/api/v1/operations/overview", route => route.fulfill({ json: {
      generated_at: "2026-09-20T00:00:00Z", stalled_after_seconds: 300,
      total_backlog_count: 0, total_stalled_count: 0, queues: [], processing: [], active_versions: [],
    } }));
    await page.route("**/api/v1/operations/failures**", route => route.fulfill({ json: {
      generated_at: "2026-09-20T00:00:00Z", lookback_seconds: 86400, total_failed_count: 0,
      total_partial_success_count: 0, total_retry_count: 0, total_stalled_count: 0, components: [],
    } }));
    let requests = 0;
    await page.route("**/api/v1/operations/demo-reset", async (route) => {
      const post = route.request().method() === "POST";
      if (post) {
        expect(route.request().postDataJSON()).toEqual({ fingerprint: "a".repeat(64) });
        requests++;
      }
      await route.fulfill({ json: { enabled: true, count: post ? 2 : requests ? 0 : 2, fingerprint: "a".repeat(64), reset_id: post ? "reset-1" : null } });
    });
    await login(page, "admin@demo.test");
    await navigateInSession(page, "/operations");
    await page.getByRole("button", { name: "DB 적재 원복" }).click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    expect(requests).toBe(0);
    await page.screenshot({ path: `../output/demo-reset-${width}.png`, fullPage: true });
    await page.getByRole("button", { name: "검토 대기로 원복" }).click();
    await expect(page.getByRole("status")).toContainText("2건을 검토 대기로");
    expect(requests).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
  });
}
