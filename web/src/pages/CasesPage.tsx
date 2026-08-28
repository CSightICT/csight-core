import { ArrowRight, BriefcaseBusiness, Plus, Search } from "lucide-react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { Card, EmptyState, Loading, PageHeader, formatDate, friendlyError } from "../components/Ui";
import { StatusBadge } from "../components/StatusBadge";
import { demoProductDisplayName, demoProductScenario, formatSyntheticPriceBand } from "../demo/productScenarioCatalog";
import { formatCommerceMoney, readSyntheticCommerceContext } from "../commerce/syntheticCommerceContext";
import { businessLabel, operationalReference } from "../presentation/businessLabels";

const REALISTIC_DEMO_V2_DATASET = "realistic-internal-demo-v2";
const REALISTIC_DEMO_V3_DATASET = "realistic-internal-demo-v3";
const ACTIVE_REVISIONS = new Set(["COMMERCE_CONTEXT_R2_E3"]);
const ACTIVE_V3_REVISIONS = new Set(["CLOSED_SET_EXPANSION_R3"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function shouldDisplayCaseOnDesk(attributes: Record<string, unknown>): boolean {
  const provenance = attributes.realistic_demo;
  if (!isRecord(provenance)) return true;
  if (provenance.dataset_id === REALISTIC_DEMO_V3_DATASET) {
    return typeof provenance.narrative_revision === "string"
      && ACTIVE_V3_REVISIONS.has(provenance.narrative_revision);
  }
  if (provenance.dataset_id !== REALISTIC_DEMO_V2_DATASET) return true;
  return typeof provenance.narrative_revision === "string"
    && ACTIVE_REVISIONS.has(provenance.narrative_revision);
}

export function CasesPage() {
  const [query, setQuery] = useState("");
  const cases = useQuery({ queryKey: ["cases"], queryFn: () => api.listCases("?page=1&page_size=100") });
  const summaries = cases.data?.items ?? [];
  const detailQueries = useQueries({
    queries: summaries.map((item) => ({
      queryKey: ["case", item.case_id],
      queryFn: () => api.getCase(item.case_id),
      retry: false,
    })),
  });
  const visibilityPending = detailQueries.some((detail) => detail.isPending);
  const visibilityErrorCount = detailQueries.filter((detail) => detail.isError).length;
  const visibleCases = summaries.filter((_item, index) => {
    const detail = detailQueries[index]?.data;
    return detail !== undefined && shouldDisplayCaseOnDesk(detail.attributes);
  });
  const value = query.trim().toLowerCase();
  const filtered = value
    ? visibleCases.filter((item) =>
      [
        item.case_id,
        item.order_ref,
        item.product_ref,
        demoProductDisplayName(item.product_ref) ?? "",
        readSyntheticCommerceContext(
          detailQueries[summaries.findIndex((candidate) => candidate.case_id === item.case_id)]?.data?.attributes,
        )?.customer.displayName ?? "",
      ].some((field) => field.toLowerCase().includes(value)),
    )
    : visibleCases;

  return <div className="page">
    <PageHeader eyebrow="문의 목록" title="접수된 문의" description="접수된 상품 문의를 확인하고 분석·정책 검토를 이어갑니다."
      actions={<Link className="button button-primary" to="/cases/new"><Plus size={18} />새 문의</Link>} />
    <Card className="table-card">
      <div className="table-toolbar">
        <label className="search-box"><Search size={18} aria-hidden="true" /><span className="sr-only">문의 검색</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="주문·상품·문의 번호 검색" /></label>
        <span className="result-count">{visibilityPending ? "확인 중" : `${filtered.length}건`}</span>
      </div>
      {visibilityErrorCount > 0 && <div className="inline-alert inline-alert-danger case-visibility-alert" role="alert">일부 문의의 시나리오 버전을 확인하지 못해 목록에서 안전하게 제외했습니다.</div>}
      {cases.isLoading || visibilityPending ? <Loading label="문의 표시 기준을 확인하는 중" /> : cases.error ? <div className="error-panel" role="alert">{friendlyError(cases.error)}</div> : filtered.length === 0 ?
        <EmptyState title="표시할 문의가 없습니다" action={<Link className="button button-secondary" to="/cases/new">첫 문의 만들기</Link>}>새 문의를 등록하면 이곳에서 진행 상태를 볼 수 있습니다.</EmptyState> :
        <div className="case-list" role="list">{filtered.map((item) => {
          const product = demoProductScenario(item.product_ref);
          const detailIndex = summaries.findIndex((candidate) => candidate.case_id === item.case_id);
          const commerce = readSyntheticCommerceContext(detailQueries[detailIndex]?.data?.attributes);
          const catalogName = demoProductDisplayName(item.product_ref);
          const productName = commerce?.order.productDisplayName ?? catalogName ?? `${operationalReference(item.product_ref)} 상품`;
          return <Link className="case-row" to={`/cases/${item.case_id}`} key={item.case_id} role="listitem">
            <span className="case-icon"><BriefcaseBusiness size={20} /></span>
            <div className="case-primary">
              <strong>{productName}</strong>
              <span>{product ? `상품 번호 ${operationalReference(product.syntheticSku)} · 가격대 ${formatSyntheticPriceBand(product)}` : `상품 번호 ${operationalReference(item.product_ref)}`}</span>
              <small>주문 번호 {item.order_ref}</small>
              {commerce && <small>{commerce.customer.displayName} · {commerce.customer.customerId} · 결제 {formatCommerceMoney(commerce.order.paidAmount, commerce.order.currency)}</small>}
            </div>
            <div className="case-action"><small>요청 유형</small><span>{businessLabel(item.requested_action)}</span></div>
            <div className="case-date"><small>접수</small><span>{formatDate(item.created_at)}</span></div>
            <StatusBadge status={item.status} /><ArrowRight size={18} className="row-arrow" />
          </Link>;
        })}</div>}
    </Card>
  </div>;
}
