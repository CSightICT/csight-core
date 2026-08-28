import { expect, test } from "@playwright/test";

import { installApi, login, navigateInSession } from "./fixtures/api";

test("1. 완전한 Repair 결정은 부작용 없는 DRY-RUN 검증 결과로 표시된다", async ({ page }) => {
  await installApi(page, "validated");
  await login(page);
  await navigateInSession(page, "/reviews/task-validated");
  await expect(page.getByTestId("quick-review-panel")).toContainText("준비도 100%");
  await expect(page.getByText("모델 정확도가 아닌 정책·근거·입력 준비도입니다.")).toBeVisible();
  await page.getByRole("button", { name: /수리 허용/ }).click();
  await page.waitForURL("**/cases/case-validated/report");
  await expect(page.getByRole("heading", { name: "최종 검토 보고서" })).toBeVisible();
  await expect(page.getByText("수리 승인")).toBeVisible();
  await expect(page.getByText("외부 시스템 반영 여부").locator("..")).toContainText("아니요");
  await navigateInSession(page, "/cases/case-validated");
  await expect(page.getByTestId("review-workbench")).toBeVisible();
  await expect(page.getByRole("heading", { name: "문의 내용" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "이미지 근거" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "정책 기반 권고" })).toBeVisible();
  await expect(page.getByTestId("fictional-inquiry-badge")).toHaveText("온라인 접수");
  await expect(page.getByText(/지난주 CSight Commerce에서 주문한 무선 청소기/)).toBeVisible();
  await expect(page.getByTestId("image-observation-boundary")).toContainText("본체 아래 브러시 하우징과 장착부 외관");
  await expect(page.getByTestId("image-observation-boundary")).toContainText("비가시 정보는 고객 진술이며 Vision 근거가 아닙니다");
  await expect(page.getByText("CSight Commerce 상품 하자 반품·교환 운영정책")).toBeVisible();
  await expect(page.getByText("사내 정책 참고 자료").first()).toBeVisible();
  await expect(page.getByTestId("policy-guidance")).toContainText("담당자 검토 필요");
  await page.getByText("결정 이후 · 처리 결과 확인").click();
  await expect(page.getByTestId("resolution-status")).toContainText("처리 사전 확인 완료");
  await expect(page.getByText("실제 부작용").locator(".." )).toContainText("없음");
  await expect(page.getByText("사전 확인 시도").locator("..")).toContainText("1");
  await expect(page.getByText("사전 확인 결과", { exact: true }).locator("..")).toContainText("1");
});

test("2. 환불 금액·통화 누락은 입력 보류이며 Attempt와 Result가 0이다", async ({ page }) => {
  await installApi(page, "needs-input");
  await login(page);
  await navigateInSession(page, "/cases/case-needs-input");
  await page.getByText("결정 이후 · 처리 결과 확인").click();
  await expect(page.getByTestId("resolution-status")).toContainText("처리 정보 보완 필요");
  await expect(page.getByText("Command·Attempt·Result를 만들지 않고 안전하게 보류합니다.")).toBeVisible();
  await expect(page.getByText("처리 요청").locator("..")).toContainText("0개");
  await expect(page.getByText("사전 확인 시도").locator("..")).toContainText("0");
  await expect(page.getByText("사전 확인 결과", { exact: true }).locator("..")).toContainText("0");
  await navigateInSession(page, "/cases/case-needs-input/report");
  await expect(page.getByRole("heading", { name: "환불 처리 확인서" }).last()).toBeVisible();
  await expect(page.getByTestId("refund-confirmation")).toContainText("환불 정보 보완 필요");
  await expect(page.getByTestId("refund-confirmation")).toContainText("환불 예정 금액입력 필요");
  await expect(page.getByTestId("refund-confirmation")).toContainText("외부 결제사 전송 없음 · 실제 환불 미실행");
  await expect(page.getByTestId("refund-confirmation")).toContainText("결제업자 취소 요청미요청 · 외부 시스템 미연결");
});

test("3. 이미지 부족 건은 추가자료 요청 상태이며 결정과 조치가 생성되지 않는다", async ({ page }) => {
  await installApi(page, "evidence");
  await login(page);
  await navigateInSession(page, "/cases/case-evidence");
  await expect(page.getByText("이미지가 없습니다")).toBeVisible();
  await page.getByText("결정 이후 · 처리 결과 확인").click();
  await expect(page.getByText("아직 처리 결과가 없습니다")).toBeVisible();
  await navigateInSession(page, "/reviews/task-evidence");
  await expect(page.getByText("추가 자료 필요", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "검토 재개" })).toBeVisible();
  await expect(page.getByRole("button", { name: "결정 확정" })).toHaveCount(0);
});

test("4. Safety Case는 검토자를 차단하고 ADMIN에게만 결정 폼을 연다", async ({ browser }) => {
  const reviewerContext = await browser.newContext();
  const reviewer = await reviewerContext.newPage();
  await installApi(reviewer, "safety");
  await login(reviewer, "reviewer@demo.test");
  await navigateInSession(reviewer, "/reviews/task-safety");
  await expect(reviewer.getByText("관리자 전용 검토")).toBeVisible();
  await expect(reviewer.getByRole("button", { name: "내가 검토하기" })).toHaveCount(0);
  await expect(reviewer.getByRole("button", { name: "결정 확정" })).toHaveCount(0);
  await reviewerContext.close();

  const adminContext = await browser.newContext();
  const admin = await adminContext.newPage();
  await installApi(admin, "safety");
  await login(admin, "admin@demo.test");
  await navigateInSession(admin, "/reviews/task-safety");
  await expect(admin.getByText("관리자 전용 검토")).toHaveCount(0);
  await expect(admin.getByTestId("quick-review-panel")).toBeVisible();
  await expect(admin.getByRole("button", { name: /환불\/반품 허용/ })).toBeVisible();
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
  await expect(page.getByText("결과 계약 확인 필요")).toBeVisible();
  await expect(page.getByTestId("binary-vision-assessment")).toHaveCount(0);
  await expect(page.getByText("E3 Runtime identity 일치")).toHaveCount(0);
  await expect(page.getByText(/자동 결정·외부 조치는 생성하지 않으며/)).toBeVisible();
  await page.getByText("결정 이후 · 처리 결과 확인").click();
  await expect(page.getByText("아직 처리 결과가 없습니다")).toBeVisible();
  await expect(page.getByText("사람 검토").first()).toBeVisible();
});
