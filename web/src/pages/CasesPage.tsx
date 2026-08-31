import { ArrowDownUp, ArrowRight, BriefcaseBusiness, Search } from "lucide-react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useOptionalAuth } from "../auth/AuthProvider";
import type { OperatorQueueSort, OperatorQueueView } from "../api/contracts";
import { OperatorQueueTabs } from "../components/OperatorQueueTabs";
import { Card, EmptyState, Loading, PageHeader, formatDate, friendlyError, shortId } from "../components/Ui";
import { StatusBadge } from "../components/StatusBadge";
import { demoProductDisplayName, demoProductScenario, formatSyntheticPriceBand } from "../demo/productScenarioCatalog";
import { formatQueueWait } from "../operator/queuePresentation";
import { businessLabel, operationalReference } from "../presentation/businessLabels";

const emptyCounts = { all: 0, my: 0, unassigned: 0, urgent: 0, waiting_evidence: 0, complete: 0 };

export function CasesPage() {
  const user = useOptionalAuth()?.user ?? null;
  const queryClient = useQueryClient();
  const isAdmin = Boolean(user?.roles.includes("ADMIN"));
  const reviewerWorkspace = Boolean(user?.roles.includes("REVIEWER") && !user.roles.includes("ADMIN"));
  const [query, setQuery] = useState("");
  const searchValue = useDeferredValue(query.trim());
  const [view, setView] = useState<OperatorQueueView>(reviewerWorkspace ? "my" : "all");
  const [sort, setSort] = useState<OperatorQueueSort>("newest");
  const cases = useInfiniteQuery({
    queryKey: ["cases", "operator", view, sort, searchValue],
    queryFn: ({ pageParam }) => api.listOperatorCases({ view, sort, q: searchValue, limit: 25, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const items = cases.data?.pages.flatMap((page) => page.items) ?? [];
  const assignees = useQuery({ queryKey: ["review-assignees"], queryFn: () => api.listReviewAssignees(), enabled: isAdmin });
  const assign = useMutation({
    mutationFn: ({ caseId, version, assigneeId }: { caseId: string; version: number; assigneeId: string }) => api.assignCase(caseId, { expected_version: version, assignee_id: assigneeId, rationale: "관리자가 문의 접수 담당자를 배정하거나 변경했습니다." }),
    onSuccess: async () => Promise.all([queryClient.invalidateQueries({ queryKey: ["cases"] }), queryClient.invalidateQueries({ queryKey: ["reviews"] })]),
  });
  const assigneeNames = new Map(assignees.data?.map((item) => [item.user_id, item.display_name]));
  const counts = cases.data?.pages[0]?.counts ?? emptyCounts;

  return <div className="page">
    <PageHeader eyebrow="문의 목록" title={reviewerWorkspace ? "문의 대기" : "접수된 문의"} description={reviewerWorkspace ? "나에게 배정되어 아직 처리가 필요한 문의입니다." : "담당자·우선순위·최근 변경 시각을 한 번에 확인하고 다음 업무를 선택합니다."} />
    <Card className="table-card operator-queue-card">
      <OperatorQueueTabs counts={counts} idPrefix="case-view" panelId="case-queue-panel" value={view} onChange={setView} {...(reviewerWorkspace ? { allowedViews: ["my"] as OperatorQueueView[] } : {})} />
      <div className="table-toolbar operator-queue-toolbar">
        <label className="search-box"><Search size={18} aria-hidden="true" /><span className="sr-only">문의 검색</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="주문·상품·문의 번호 검색" /></label>
        <label className="filter-control"><ArrowDownUp size={17} aria-hidden="true" /><span>정렬</span><select aria-label="문의 정렬" value={sort} onChange={(event) => setSort(event.target.value as OperatorQueueSort)}><option value="newest">새 문의순</option><option value="oldest">오래된 문의순</option></select></label>
        <span className="result-count">{searchValue ? "검색 결과 " : "총 "}{counts[view]}건</span>
      </div>
      <div id="case-queue-panel" role="tabpanel" aria-labelledby={`case-view-${view}`} tabIndex={0}>
        {assign.isError && <div className="inline-alert inline-alert-danger queue-page-error" role="alert">{friendlyError(assign.error)} 최신 목록을 확인한 뒤 다시 배정해 주세요.</div>}
        {cases.isPending ? <Loading label="문의 업무 목록을 불러오는 중" /> : cases.isError && !items.length ? <div className="error-panel" role="alert">{friendlyError(cases.error)}</div> : items.length === 0 ?
          <EmptyState title={searchValue ? "검색 결과가 없습니다" : "해당 업무가 없습니다"}>{searchValue ? "검색어를 바꾸거나 다른 업무 보기를 선택해 주세요." : "다른 업무 보기를 선택해 주세요. 새 문의는 연결된 접수 채널에서 자동으로 들어옵니다."}</EmptyState> :
          <div className="case-list" role="list">{items.map((item) => {
            const product = demoProductScenario(item.product_ref);
            const productName = demoProductDisplayName(item.product_ref) ?? `${operationalReference(item.product_ref)} 상품`;
            return <div className="review-row-shell" key={item.case_id} role="listitem"><Link className="case-row operator-case-row" to={`/cases/${item.case_id}`}>
              <span className="case-icon"><BriefcaseBusiness size={20} /></span>
              <div className="case-primary">
                <strong>{productName}</strong>
                <span>{product ? `상품 번호 ${operationalReference(product.syntheticSku)} · 가격대 ${formatSyntheticPriceBand(product)}` : `상품 번호 ${operationalReference(item.product_ref)}`}</span>
                <small>주문 번호 {item.order_ref} · 문의 {shortId(item.case_id)}</small>
                <small className="operator-mobile-meta">담당자 {item.assignee_id ? shortId(item.assignee_id) : "미배정"} · 최근 변경 {formatDate(item.updated_at)} · 대기 {formatQueueWait(item.updated_at)}</small>
              </div>
              <div className="case-action"><small>요청 유형</small><span>{businessLabel(item.requested_action)}</span></div>
              <div className="queue-assignee"><small>담당자</small><span title={item.assignee_id ?? undefined}>{item.assignee_id ? assigneeNames.get(item.assignee_id) ?? shortId(item.assignee_id) : "미배정"}</span><small>{item.review_status ? businessLabel(item.review_status) : "검토 작업 없음"}</small></div>
              <div className="queue-updated"><small>최근 변경</small><span>{formatDate(item.updated_at)}</span><small>대기 {formatQueueWait(item.updated_at)}</small></div>
              <StatusBadge status={item.case_status} /><ArrowRight size={18} className="row-arrow" />
            </Link>{isAdmin && item.case_status !== "RESOLVED" && <div className="review-assignment-control"><label><span>문의 담당자</span><select aria-label={`${shortId(item.case_id)} 문의 담당자`} value={item.assignee_id ?? ""} disabled={assign.isPending || assignees.isPending} onChange={(event) => { if (event.target.value && event.target.value !== item.assignee_id) assign.mutate({ caseId: item.case_id, version: item.assignment_version, assigneeId: event.target.value }); }}><option value="" disabled>담당자 선택</option>{assignees.data?.map((assignee) => <option value={assignee.user_id} key={assignee.user_id}>{assignee.display_name}</option>)}</select></label></div>}</div>;
          })}</div>}
        {cases.isFetchNextPageError && <div className="inline-alert inline-alert-danger queue-page-error" role="alert">다음 문의를 불러오지 못했습니다. 현재 목록은 그대로 유지됩니다.</div>}
        {cases.hasNextPage && <div className="queue-more"><button className="button button-secondary" type="button" disabled={cases.isFetchingNextPage} onClick={() => { void cases.fetchNextPage(); }}>{cases.isFetchingNextPage ? "더 불러오는 중…" : "문의 더 보기"}</button></div>}
      </div>
    </Card>
  </div>;
}
