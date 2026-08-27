import { ArrowRight, BriefcaseBusiness, Plus, Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { Card, EmptyState, Loading, PageHeader, formatDate, friendlyError } from "../components/Ui";
import { StatusBadge } from "../components/StatusBadge";

export function CasesPage() {
  const [query, setQuery] = useState("");
  const cases = useQuery({ queryKey: ["cases"], queryFn: () => api.listCases("?page=1&page_size=100") });
  const filtered = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return cases.data?.items ?? [];
    return (cases.data?.items ?? []).filter((item) =>
      [item.case_id, item.order_ref, item.product_ref].some((field) => field.toLowerCase().includes(value)),
    );
  }, [cases.data, query]);

  return <div className="page">
    <PageHeader eyebrow="Case desk" title="상담 케이스" description="접수된 건을 확인하고 분석·정책 검토 흐름을 이어갑니다."
      actions={<Link className="button button-primary" to="/cases/new"><Plus size={18} />새 케이스</Link>} />
    <Card className="table-card">
      <div className="table-toolbar">
        <label className="search-box"><Search size={18} aria-hidden="true" /><span className="sr-only">케이스 검색</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="주문·상품·케이스 ID 검색" /></label>
        <span className="result-count">{filtered.length}건</span>
      </div>
      {cases.isLoading ? <Loading label="케이스를 불러오는 중" /> : cases.error ? <div className="error-panel" role="alert">{friendlyError(cases.error)}</div> : filtered.length === 0 ?
        <EmptyState title="표시할 케이스가 없습니다" action={<Link className="button button-secondary" to="/cases/new">첫 케이스 만들기</Link>}>새 상담 건을 등록하면 이곳에서 진행 상태를 볼 수 있습니다.</EmptyState> :
        <div className="case-list" role="list">{filtered.map((item) => <Link className="case-row" to={`/cases/${item.case_id}`} key={item.case_id} role="listitem">
          <span className="case-icon"><BriefcaseBusiness size={20} /></span>
          <div className="case-primary"><strong>{item.order_ref}</strong><span>{item.product_ref}</span></div>
          <div className="case-action"><small>요청</small><span>{item.requested_action}</span></div>
          <div className="case-date"><small>접수</small><span>{formatDate(item.created_at)}</span></div>
          <StatusBadge status={item.status} /><ArrowRight size={18} className="row-arrow" />
        </Link>)}</div>}
    </Card>
  </div>;
}
