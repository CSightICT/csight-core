import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PolicyCitationSnapshot } from "../api/contracts";
import { PolicyCitationList } from "./PolicyCitationList";

const citation: PolicyCitationSnapshot = {
  citation_id: "CIT-001",
  rank: 1,
  policy_clause_id: "returns.damage.01",
  document_id: "returns-policy",
  document_version: "2026.08",
  title: "파손 상품 접수 및 검토 기준",
  section_path: ["상품 하자", "파손"],
  clause_type: "ELIGIBILITY",
  text: "배송 중 파손이 의심되는 경우 사진 증거와 주문 정보를 함께 검토한다.",
};

describe("PolicyCitationList", () => {
  it("shows citation-pack title, body, and immutable document version as policy evidence", () => {
    render(<PolicyCitationList citations={[citation]} />);

    expect(screen.getByText(citation.title)).toBeVisible();
    expect(screen.getByText(citation.text)).toBeVisible();
    expect(screen.getByText(`문서 버전 ${citation.document_version}`)).toBeVisible();
    expect(screen.getByTestId("synthetic-policy-badge")).toHaveTextContent("가상 사내 정책 · PoC 전용");
    expect(screen.getByText(/그 자체로 승인·환불·교환 결정을 만들지 않습니다/)).toBeVisible();
  });
});
