import { ArrowRight, ClipboardCheck, Filter } from "lucide-react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { Card, EmptyState, Loading, PageHeader, formatDate, friendlyError, shortId } from "../components/Ui";
import { StatusBadge } from "../components/StatusBadge";
import { readSyntheticCommerceContext } from "../commerce/syntheticCommerceContext";
import { demoProductDisplayName } from "../demo/productScenarioCatalog";
import { businessLabel } from "../presentation/businessLabels";

const filters = ["ACTIVE", "PENDING", "CLAIMED", "WAITING_FOR_EVIDENCE", "ESCALATED", "RESOLVED"];

export function ReviewsPage() {
  const [filter, setFilter] = useState("ACTIVE");
  const query = filter === "ACTIVE" ? "" : `?status=${encodeURIComponent(filter)}`;
  const tasks = useQuery({ queryKey: ["reviews", filter], queryFn: () => api.listReviewTasks(query) });
  const visible = filter === "ACTIVE" ? (tasks.data ?? []).filter((task) => task.status !== "RESOLVED") : tasks.data ?? [];
  const caseQueries = useQueries({
    queries: visible.map((task) => ({
      queryKey: ["case", task.case_id],
      queryFn: () => api.getCase(task.case_id),
      retry: false,
    })),
  });
  return <div className="page">
    <PageHeader eyebrow="담당자 검토" title="검토 대기함" description="정책 권고와 근거를 확인하고 최종 결정을 기록합니다." />
    <Card className="table-card">
      <div className="table-toolbar">
        <label className="filter-control"><Filter size={17} /><span>상태</span><select value={filter} onChange={(event) => setFilter(event.target.value)}>{filters.map((item) => <option value={item} key={item}>{businessLabel(item)}</option>)}</select></label>
        <span className="result-count">{visible.length}건</span>
      </div>
      {tasks.isLoading ? <Loading label="검토 작업을 불러오는 중" /> : tasks.error ? <div className="error-panel" role="alert">{friendlyError(tasks.error)}</div> : visible.length === 0 ? <EmptyState title="해당 검토 작업이 없습니다"><span>정책 평가가 완료된 케이스가 이곳에 들어옵니다.</span></EmptyState> :
        <div className="case-list" role="list">{visible.map((task, index) => {
          const caseDetail = caseQueries[index]?.data;
          const commerce = readSyntheticCommerceContext(caseDetail?.attributes);
          const productName = commerce?.order.productDisplayName
            ?? (caseDetail ? demoProductDisplayName(caseDetail.product_ref) : undefined)
            ?? (caseQueries[index]?.isError ? "상품 정보 확인 필요" : "상품명 확인 중");
          return <Link className="case-row review-row" to={`/reviews/${task.id}`} key={task.id} role="listitem">
            <span className="case-icon"><ClipboardCheck size={20} /></span>
            <div className="case-primary"><strong>{productName}</strong><span>{businessLabel(task.task_type)} · 문의 번호 {shortId(task.case_id)}</span></div>
            <div className="case-action"><small>우선순위</small><span>{businessLabel(task.priority)}</span></div>
            <div className="case-date"><small>업데이트</small><span>{formatDate(task.updated_at)}</span></div>
            <StatusBadge status={task.status} /><ArrowRight className="row-arrow" size={18} />
          </Link>;
        })}</div>}
    </Card>
  </div>;
}
