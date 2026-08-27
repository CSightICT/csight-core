import { expect, test } from "@playwright/test";

import { installApi, login, navigateInSession } from "./fixtures/api";

test("1. 완전한 Repair 결정은 부작용 없는 DRY-RUN 검증 결과로 표시된다", async ({ page }) => {
  await installApi(page, "validated");
  await login(page);
  await navigateInSession(page, "/cases/case-validated");
  await expect(page.getByTestId("resolution-status")).toContainText("ACTION_DRY_RUN_VALIDATED");
  await expect(page.getByText("실제 부작용").locator(".." )).toContainText("없음");
  await expect(page.getByText("Simulation Attempt").locator("..")).toContainText("1");
  await expect(page.getByText("Simulation Result").locator("..")).toContainText("1");
});

test("2. 환불 금액·통화 누락은 입력 보류이며 Attempt와 Result가 0이다", async ({ page }) => {
  await installApi(page, "needs-input");
  await login(page);
  await navigateInSession(page, "/cases/case-needs-input");
  await expect(page.getByTestId("resolution-status")).toContainText("ACTION_NEEDS_INPUT");
  await expect(page.getByText("Command·Attempt·Result를 만들지 않고 안전하게 보류합니다.")).toBeVisible();
  await expect(page.getByText("Action Intent").locator("..")).toContainText("0개");
  await expect(page.getByText("Simulation Attempt").locator("..")).toContainText("0");
  await expect(page.getByText("Simulation Result").locator("..")).toContainText("0");
});

test("3. 이미지 부족 건은 추가자료 요청 상태이며 결정과 조치가 생성되지 않는다", async ({ page }) => {
  await installApi(page, "evidence");
  await login(page);
  await navigateInSession(page, "/cases/case-evidence");
  await expect(page.getByText("이미지가 없습니다")).toBeVisible();
  await expect(page.getByText("아직 Resolution이 없습니다")).toBeVisible();
  await navigateInSession(page, "/reviews/task-evidence");
  await expect(page.getByText("추가 자료 필요")).toBeVisible();
  await expect(page.getByRole("button", { name: "검토 재개" })).toBeVisible();
  await expect(page.getByRole("button", { name: "결정 확정" })).toHaveCount(0);
});

test("4. Safety Case는 검토자를 차단하고 ADMIN에게만 결정 폼을 연다", async ({ browser }) => {
  const reviewerContext = await browser.newContext();
  const reviewer = await reviewerContext.newPage();
  await installApi(reviewer, "safety");
  await login(reviewer, "reviewer@demo.test");
  await navigateInSession(reviewer, "/reviews/task-safety");
  await expect(reviewer.getByText("Safety Case 권한 차단")).toBeVisible();
  await expect(reviewer.getByRole("button", { name: "내가 검토하기" })).toHaveCount(0);
  await expect(reviewer.getByRole("button", { name: "결정 확정" })).toHaveCount(0);
  await reviewerContext.close();

  const adminContext = await browser.newContext();
  const admin = await adminContext.newPage();
  await installApi(admin, "safety");
  await login(admin, "admin@demo.test");
  await navigateInSession(admin, "/reviews/task-safety");
  await expect(admin.getByText("Safety Case 권한 차단")).toHaveCount(0);
  await expect(admin.getByRole("button", { name: "결정 확정" })).toBeVisible();
  await adminContext.close();
});

test("5. Vision timeout은 별도 부분 완료로 표시되고 자동 결정·조치를 만들지 않는다", async ({ page }) => {
  await installApi(page, "vision-timeout");
  await login(page);
  await page.evaluate(() => sessionStorage.setItem("csight.workflow.v1", JSON.stringify({
    caseId: "case-vision-timeout", visionRunId: "vision-vision-timeout", idempotencyKeys: { vision: "vision-key-1" },
  })));
  await navigateInSession(page, "/cases/case-vision-timeout");
  await expect(page.getByTestId("vision-result")).toContainText("부분 완료");
  await expect(page.getByText(/자동 결정·외부 조치는 생성하지 않으며/)).toBeVisible();
  await expect(page.getByText("아직 Resolution이 없습니다")).toBeVisible();
  await expect(page.getByText("사람 검토").first()).toBeVisible();
});
