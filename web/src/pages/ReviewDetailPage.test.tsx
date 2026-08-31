import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "../api/client";
import type { CaseDetail, ReviewTaskDetail } from "../api/contracts";
import * as AuthProvider from "../auth/AuthProvider";
import { ReviewDetailPage } from "./ReviewDetailPage";

const now = "2026-08-29T00:00:00Z";

function reviewDetail(status = "PENDING", version = 1, decision: Record<string, unknown> | null = null): ReviewTaskDetail {
  return {
    task: {
      id: "task-1",
      case_id: "case-1",
      policy_evaluation_run_id: "policy-1",
      task_type: "STANDARD_REVIEW",
      priority: "NORMAL",
      status,
      current_assignee_id: status === "CLAIMED" ? "user-1" : null,
      version,
      mapping_rule_name: "policy_evaluation_to_human_review",
      mapping_rule_version: "1.0.0",
      created_at: now,
      updated_at: now,
      resolved_at: status === "RESOLVED" ? now : null,
    },
    packet: {
      policy_summary_status: "REQUIRES_HUMAN_REVIEW",
      qualification_snapshot: { llm: { scope: "MOCK_QUALIFIED" }, grounding: { scope: "LOCAL_POC" } },
      policy_effects: [{ type: "MARK_REVIEW_ELIGIBILITY", value: "REPAIR_REVIEW" }],
    },
    actions: [],
    decision,
    rule_results: [{ id: "rule-result-1", rule_id: "CSCC-DEFECT-04", status: "MATCHED" }],
    citation_items: [{ citation_id: "citation-1", clause_id: "CSCC-OPS-4.2", text: "담당자가 주문과 증거를 확인합니다." }],
  grounded_explanation: null,
  inquiry_summary: "포장을 개봉하지 않은 상품의 환불 요청입니다.",
  policy_similarity: [],
  };
}

const caseDetail: CaseDetail = {
  case_id: "case-1",
  tenant_id: "tenant-1",
  domain_type: "product_defect_cs",
  status: "REVIEW_PENDING",
  order_ref: "ORD-2026-100",
  product_ref: "SKU-CLEANER-1",
  requested_action: "REPAIR",
  customer_message: "브러시가 회전하지 않아 수리를 요청합니다.",
  attributes: {},
  created_by: "user-1",
  evidence: [],
  status_history: [],
  latest_analysis_run: null,
  created_at: now,
  updated_at: now,
};

const imageEvidence: CaseDetail["evidence"][number] = {
  evidence_id: "evidence-1",
  tenant_id: "tenant-1",
  case_id: "case-1",
  evidence_type: "IMAGE",
  upload_status: "AVAILABLE",
  original_filename: "customer-photo-1.jpg",
  content_type: "image/jpeg",
  size_bytes: 1024,
  sha256: "a".repeat(64),
  width: 100,
  height: 100,
  created_by: "user-1",
  created_at: now,
  updated_at: now,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/reviews/task-1"]}><Routes>
    <Route path="/reviews/:taskId" element={<ReviewDetailPage />} />
    <Route path="/cases/:caseId/report" element={<p>보고서 화면</p>} />
  </Routes></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  let objectUrlIndex = 0;
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => `blob:https://doongdoong.org/review-evidence-${objectUrlIndex += 1}`),
  });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  vi.spyOn(AuthProvider, "useAuth").mockReturnValue({
    user: { user_id: "user-1", tenant_id: "tenant-1", email: "reviewer@test.local", display_name: "검토자", roles: ["REVIEWER"] },
    busy: false,
    sessionExpired: false,
    sessionExpiresWithinFiveMinutes: false,
    oidcAvailable: false,
    legacyPasswordAvailable: true,
    login: vi.fn(async () => undefined),
    startOidcLogin: vi.fn(),
    logout: vi.fn(async () => undefined),
    hasRole: (role: string) => role === "REVIEWER",
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ReviewDetailPage quick decision confirmation", () => {
  it("presents evidence, inquiry, policy basis, and three-by-three similarity in one summary", async () => {
    const current = reviewDetail();
    current.grounded_explanation = {
      explanation: "미사용 상품 환불 조항과 접수 내용이 일치하는지 담당자가 확인해야 합니다.",
    };
    current.citation_items = [{
      citation_id: "citation-1",
      policy_clause_id: "CSCC-RETURN-4.2",
      title: "미사용 상품 반품 정책",
      section_path: "반품 > 미사용 상품",
      text: "배송 완료 후 정해진 기간 안에 미사용 상품의 반품을 검토할 수 있습니다.",
    }];
    current.policy_similarity = [
      ...[0.66, 0.63, 0.69].map((score, index) => ({
        group: "NEAREST" as const,
        rank: index + 1,
        cosine_similarity: score,
        reference_threshold: 0.65,
        threshold_version: "policy_similarity_reference/1.0.0",
        reason_codes: ["REFERENCE_DISTANCE_NEAREST"],
        policy_clause_id: `near-${index + 1}`,
        title: `가까운 정책 ${index + 1}`,
        text: `임계값과 가까운 정책 내용 ${index + 1}`,
      })),
      ...[0.03, 0.08, 0.12].map((score, index) => ({
        group: "LEAST" as const,
        rank: index + 1,
        cosine_similarity: score,
        reference_threshold: 0.65,
        threshold_version: "policy_similarity_reference/1.0.0",
        reason_codes: ["LOWEST_COSINE_SIMILARITY"],
        policy_clause_id: `least-${index + 1}`,
        title: `부적합 정책 ${index + 1}`,
        text: `문의 맥락과 다른 정책 내용 ${index + 1}`,
      })),
    ];
    vi.spyOn(api, "getReviewTask").mockResolvedValue(current);
    vi.spyOn(api, "getCase").mockResolvedValue(caseDetail);

    renderPage();

    expect(await screen.findByRole("heading", { name: "문의 검토 요약" })).toBeVisible();
    expect(screen.getByRole("link", { name: /내 문의 처리 현황/ })).toBeVisible();
    expect(screen.getByRole("heading", { name: "고객 첨부 사진" })).toBeVisible();
    expect(screen.getByText("포장을 개봉하지 않은 상품의 환불 요청입니다.")).toBeVisible();
    expect(screen.getByText("미사용 상품 환불 조항과 접수 내용이 일치하는지 담당자가 확인해야 합니다.")).toBeVisible();
    expect(screen.getByText("배송 완료 후 정해진 기간 안에 미사용 상품의 반품을 검토할 수 있습니다.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "임계값에 가장 가까운 정책 3개" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "가장 부적합한 정책 3개" })).toBeVisible();
    expect(screen.getAllByText(/부적격 이유:/)).toHaveLength(3);
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("distinguishes a failed case load from no attachments and blocks a manual final decision", async () => {
    vi.spyOn(api, "getReviewTask").mockResolvedValue(reviewDetail("CLAIMED", 2));
    vi.spyOn(api, "getCase").mockRejectedValue(new Error("case unavailable"));

    renderPage();
    const user = userEvent.setup();

    expect(await screen.findByText(/문의와 첨부 사진을 불러오지 못했습니다/)).toBeVisible();
    expect(screen.queryByText("첨부 사진이 없습니다.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "문의와 사진 다시 불러오기" })).toBeVisible();

    await user.click(screen.getByText("상세 결정 또는 자료 요청"));
    expect(screen.getByText("문의와 첨부 사진을 정상적으로 불러온 뒤에만 최종 결정을 기록할 수 있습니다.")).toBeVisible();
    expect(screen.getByRole("button", { name: "결정 확정" })).toBeDisabled();
  });

  it("blocks quick and manual decisions when any required image cannot be loaded", async () => {
    vi.spyOn(api, "getReviewTask").mockResolvedValue(reviewDetail("CLAIMED", 2));
    vi.spyOn(api, "getCase").mockResolvedValue({
      ...caseDetail,
      evidence: [imageEvidence, { ...imageEvidence, evidence_id: "evidence-2", original_filename: "customer-photo-2.jpg" }],
    });
    vi.spyOn(api, "getEvidenceContent").mockImplementation(async (_caseId, evidenceId) => {
      if (evidenceId === "evidence-2") throw new Error("image unavailable");
      return new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xd9])], { type: "image/jpeg" });
    });
    const resolve = vi.spyOn(api, "resolveReview");

    renderPage();
    const user = userEvent.setup();
    const loadedImage = await screen.findByRole("img", { name: "customer-photo-1.jpg 증거 미리보기" });
    fireEvent.load(loadedImage);
    expect(await screen.findByText("확인할 수 없는 사진이 있습니다")).toBeVisible();

    await user.click(screen.getByText("상세 결정 또는 자료 요청"));
    expect(screen.getByRole("button", { name: "결정 확정" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /수리 허용/ }));
    const dialog = await screen.findByRole("alertdialog", { name: /수리 승인/ });
    expect(within(dialog).getByText("사진 확인 실패 · 최종 결정 잠김")).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "수리 승인 최종 결정 기록" })).toBeDisabled();
    expect(resolve).not.toHaveBeenCalled();
  });

  it("unlocks decisions only after a failed image is retried and decoded successfully", async () => {
    let attempt = 0;
    vi.spyOn(api, "getReviewTask").mockResolvedValue(reviewDetail("CLAIMED", 2));
    vi.spyOn(api, "getCase").mockResolvedValue({ ...caseDetail, evidence: [imageEvidence] });
    vi.spyOn(api, "getEvidenceContent").mockImplementation(async () => {
      attempt += 1;
      if (attempt === 1) throw new Error("temporary image failure");
      return new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xd9])], { type: "image/jpeg" });
    });

    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /다시 시도/ }));
    const image = await screen.findByRole("img", { name: "customer-photo-1.jpg 증거 미리보기" });
    fireEvent.load(image);
    await waitFor(() => expect(screen.queryByText("확인할 수 없는 사진이 있습니다")).not.toBeInTheDocument());

    await user.click(screen.getByText("상세 결정 또는 자료 요청"));
    expect(screen.getByRole("button", { name: "결정 확정" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /수리 허용/ }));
    const dialog = await screen.findByRole("alertdialog", { name: /수리 승인/ });
    const dialogImage = within(dialog).getByRole("img", { name: "customer-photo-1.jpg 증거 미리보기" });
    expect(within(dialog).getByRole("button", { name: "수리 승인 최종 결정 기록" })).toBeDisabled();
    fireEvent.load(dialogImage);
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "수리 승인 최종 결정 기록" })).toBeEnabled());
  });

  it("keeps summary and confirmation image states isolated when dialog decoding fails", async () => {
    vi.spyOn(api, "getReviewTask").mockResolvedValue(reviewDetail("CLAIMED", 2));
    vi.spyOn(api, "getCase").mockResolvedValue({ ...caseDetail, evidence: [imageEvidence] });
    vi.spyOn(api, "getEvidenceContent").mockResolvedValue(
      new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xd9])], { type: "image/jpeg" }),
    );

    renderPage();
    const user = userEvent.setup();
    const summaryImage = await screen.findByRole("img", { name: "customer-photo-1.jpg 증거 미리보기" });
    fireEvent.load(summaryImage);
    await user.click(screen.getByText("상세 결정 또는 자료 요청"));
    expect(screen.getByRole("button", { name: "결정 확정" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /수리 허용/ }));
    const dialog = await screen.findByRole("alertdialog", { name: /수리 승인/ });
    fireEvent.error(within(dialog).getByRole("img", { name: "customer-photo-1.jpg 증거 미리보기" }));
    expect(await within(dialog).findByText("사진 확인 실패 · 최종 결정 잠김")).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "수리 승인 최종 결정 기록" })).toBeDisabled();

    await user.click(within(dialog).getByRole("button", { name: "취소" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "결정 확정" })).toBeEnabled();
  });

  it("keeps the first click and cancel read-only, then records only after explicit confirmation", async () => {
    let current = reviewDetail();
    vi.spyOn(api, "getReviewTask").mockImplementation(async () => current);
    vi.spyOn(api, "getCase").mockResolvedValue(caseDetail);
    const claim = vi.spyOn(api, "reviewAction").mockImplementation(async (_taskId, action) => {
      expect(action).toBe("claim");
      current = reviewDetail("CLAIMED", 2);
      return { task: current.task, decision: null };
    });
    const resolve = vi.spyOn(api, "resolveReview").mockImplementation(async (_taskId, input) => {
      current = reviewDetail("RESOLVED", 3, { decision: input.decision, rationale: input.rationale });
      return { task: current.task, decision: current.decision };
    });
    vi.spyOn(api, "getReport").mockRejectedValue(new ApiError({
      status: 404, code: "REVIEW_REPORT_NOT_FOUND", message: "문서 생성 중", details: null,
    }));

    renderPage();
    const user = userEvent.setup();
    const allow = await screen.findByRole("button", { name: /수리 허용/ });
    await user.click(allow);

    const dialog = await screen.findByRole("alertdialog", { name: /수리 승인/ });
    expect(within(dialog).getByText("브러시가 회전하지 않아 수리를 요청합니다.")).toBeVisible();
    expect(within(dialog).getByText("ORD-2026-100")).toBeVisible();
    expect(within(dialog).getByText("제출된 증거가 없습니다")).toBeVisible();
    expect(within(dialog).getByText("담당자가 고정된 정책 규칙과 인용 근거를 확인하고 요청 처리를 허용했습니다.")).toBeVisible();
    expect(within(dialog).getAllByText("참고용 분석 결과 준비", { exact: true })).toHaveLength(2);
    expect(claim).not.toHaveBeenCalled();
    expect(resolve).not.toHaveBeenCalled();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(allow).toHaveFocus();
    expect(claim).not.toHaveBeenCalled();
    expect(resolve).not.toHaveBeenCalled();

    await user.click(allow);
    const reopened = await screen.findByRole("alertdialog", { name: /수리 승인/ });
    await user.click(within(reopened).getByRole("button", { name: "취소" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(claim).not.toHaveBeenCalled();
    expect(resolve).not.toHaveBeenCalled();

    await user.click(allow);
    const confirmed = await screen.findByRole("alertdialog", { name: /수리 승인/ });
    await user.click(within(confirmed).getByRole("button", { name: "수리 승인 최종 결정 기록" }));

    await waitFor(() => expect(resolve).toHaveBeenCalledTimes(1));
    expect(claim).toHaveBeenCalledTimes(1);
    expect(resolve).toHaveBeenCalledWith("task-1", {
      expected_version: 2,
      decision: "APPROVE_REPAIR",
      reason_codes: ["POLICY_CONDITION_MET"],
      rationale: "담당자가 고정된 정책 규칙과 인용 근거를 확인하고 요청 처리를 허용했습니다.",
      basis: [
        { type: "POLICY_RULE_RESULT", reference_id: "rule-result-1" },
        { type: "POLICY_CITATION", reference_id: "citation-1" },
      ],
    });
    expect(await screen.findByText("결정 기록 완료 · 문서 생성 중")).toBeVisible();
  });

  it("re-reads a 409 result and never sends a second decision when the immutable decision already exists", async () => {
    let current = reviewDetail();
    vi.spyOn(api, "getReviewTask").mockImplementation(async () => current);
    vi.spyOn(api, "getCase").mockResolvedValue(caseDetail);
    vi.spyOn(api, "reviewAction").mockImplementation(async () => {
      current = reviewDetail("CLAIMED", 2);
      return { task: current.task, decision: null };
    });
    const resolve = vi.spyOn(api, "resolveReview").mockImplementation(async () => {
      current = reviewDetail("RESOLVED", 3, { decision: "APPROVE_REPAIR", rationale: "이미 기록됨" });
      throw new ApiError({ status: 409, code: "REVIEW_TASK_VERSION_CONFLICT", message: "version conflict", details: null });
    });
    vi.spyOn(api, "getReport").mockRejectedValue(new ApiError({
      status: 404, code: "REVIEW_REPORT_NOT_FOUND", message: "문서 생성 중", details: null,
    }));

    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /수리 허용/ }));
    const dialog = await screen.findByRole("alertdialog", { name: /수리 승인/ });
    await user.click(within(dialog).getByRole("button", { name: "수리 승인 최종 결정 기록" }));

    expect(await screen.findByText(/최신 검토 상태에서 최종 결정 기록을 확인했습니다/)).toBeVisible();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(resolve).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("결정 기록 완료 · 문서 생성 중")).toBeVisible();
  });

  it("blocks re-submission after an ambiguous response until a fresh read succeeds", async () => {
    let current = reviewDetail();
    let reviewReads = 0;
    vi.spyOn(api, "getReviewTask").mockImplementation(async () => {
      reviewReads += 1;
      if (reviewReads === 2) throw new Error("network unavailable");
      return current;
    });
    vi.spyOn(api, "getCase").mockResolvedValue(caseDetail);
    vi.spyOn(api, "reviewAction").mockImplementation(async () => {
      current = reviewDetail("CLAIMED", 2);
      return { task: current.task, decision: null };
    });
    const resolve = vi.spyOn(api, "resolveReview").mockRejectedValue(new Error("response lost"));

    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /수리 허용/ }));
    const dialog = await screen.findByRole("alertdialog", { name: /수리 승인/ });
    await user.click(within(dialog).getByRole("button", { name: "수리 승인 최종 결정 기록" }));

    const recheck = await screen.findByRole("button", { name: "최신 상태 다시 확인" });
    expect(screen.getByText(/결정을 다시 보내지 말고/)).toBeVisible();
    expect(screen.getByRole("button", { name: "수리 승인 최종 결정 기록" })).toBeDisabled();
    expect(resolve).toHaveBeenCalledTimes(1);

    await user.click(recheck);
    expect(await screen.findByText(/최신 상태에서 결정이 기록되지 않은 것을 확인했습니다/)).toBeVisible();
    expect(screen.getByRole("button", { name: "수리 승인 최종 결정 기록" })).toBeEnabled();
    expect(resolve).toHaveBeenCalledTimes(1);
  });
});
