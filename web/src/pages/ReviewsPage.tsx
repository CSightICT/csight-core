import { ArrowDownUp, ArrowRight, ClipboardCheck, Search } from "lucide-react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useOptionalAuth } from "../auth/AuthProvider";
import type { OperatorQueueSort, OperatorQueueView } from "../api/contracts";
import { OperatorQueueTabs } from "../components/OperatorQueueTabs";
import { Card, EmptyState, Loading, PageHeader, formatDate, friendlyError, shortId } from "../components/Ui";
import { StatusBadge } from "../components/StatusBadge";
import { formatQueueWait } from "../operator/queuePresentation";
import { businessLabel, inquiryTitle } from "../presentation/businessLabels";

const emptyCounts = { all: 0, my: 0, unassigned: 0, urgent: 0, waiting_evidence: 0, complete: 0 };

export function ReviewsPage() {
  const user = useOptionalAuth()?.user ?? null;
  const isAdmin = Boolean(user?.roles.includes("ADMIN"));
  const reviewerWorkspace = Boolean(user?.roles.includes("REVIEWER") && !isAdmin);
  const [query, setQuery] = useState("");
  const searchValue = useDeferredValue(query.trim());
  const [view, setView] = useState<OperatorQueueView>(reviewerWorkspace ? "complete" : "all");
  const [sort, setSort] = useState<OperatorQueueSort>("newest");
  const tasks = useInfiniteQuery({
    queryKey: ["reviews", "operator", view, sort, searchValue],
    queryFn: ({ pageParam }) => api.listOperatorReviews({ view, sort, q: searchValue, limit: 25, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const items = tasks.data?.pages.flatMap((page) => page.items) ?? [];
  const assignees = useQuery({ queryKey: ["review-assignees"], queryFn: () => api.listReviewAssignees(), enabled: isAdmin });
  const assigneeNames = new Map(assignees.data?.map((item) => [item.user_id, item.display_name]));
  const counts = tasks.data?.pages[0]?.counts ?? emptyCounts;

  return <div className={isAdmin ? "page inquiry-queue-admin" : "page inquiry-queue-personal"}>
    <PageHeader eyebrow="담당자 검토" title={reviewerWorkspace ? "내 문의 처리 현황" : "검토 대기함"} description={reviewerWorkspace ? "내가 최종 처리한 문의와 결정 기록을 확인합니다." : "문의 유형을 확인하고 바로 검토하세요."} />
    <Card className="table-card operator-queue-card">
      <OperatorQueueTabs counts={counts} idPrefix="review-view" panelId="review-queue-panel" value={view} onChange={setView} {...(reviewerWorkspace ? { allowedViews: ["complete"] as OperatorQueueView[] } : {})} />
      <div className="table-toolbar operator-queue-toolbar">
        <label className="search-box"><Search size={18} aria-hidden="true" /><span className="sr-only">검토 검색</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="주문·상품·문의 번호 검색" /></label>
        <label className="filter-control"><ArrowDownUp size={17} aria-hidden="true" /><span>정렬</span><select aria-label="검토 정렬" value={sort} onChange={(event) => setSort(event.target.value as OperatorQueueSort)}><option value="newest">새 검토순</option><option value="oldest">오래된 검토순</option></select></label>
        <span className="result-count">{searchValue ? "검색 결과 " : "총 "}{counts[view]}건</span>
      </div>
      <div id="review-queue-panel" role="tabpanel" aria-labelledby={`review-view-${view}`} tabIndex={0}>
        {tasks.isPending ? <Loading label="검토 업무 목록을 불러오는 중" /> : tasks.isError && !items.length ? <div className="error-panel" role="alert">{friendlyError(tasks.error)}</div> : items.length === 0 ? <EmptyState title={searchValue ? "검색 결과가 없습니다" : "해당 검토 작업이 없습니다"}><span>{searchValue ? "검색어를 바꾸거나 다른 업무 보기를 선택해 주세요." : "다른 업무 보기를 선택하거나 새로운 정책 평가 결과를 기다려 주세요."}</span></EmptyState> :
          <div className="case-list" role="list">{items.map((task) => {
            return <div className="review-row-shell" key={task.review_task_id} role="listitem"><Link className="case-row operator-case-row review-row inquiry-queue-row" to={`/reviews/${task.review_task_id}`}>
              <span className="case-icon"><ClipboardCheck size={20} /></span>
              <div className="case-primary"><strong>{task.inquiry_preview?.trim() || inquiryTitle(task.requested_action)}</strong><span>{businessLabel(task.requested_action)} · 문의 {shortId(task.case_id)} · 대기 {formatQueueWait(task.updated_at)}</span>{["HIGH", "CRITICAL"].includes(task.priority) && <small>우선 검토 · {businessLabel(task.priority)}</small>}</div>
              {isAdmin && <div className="queue-assignee"><small>담당자</small><span>{task.assignee_id ? assigneeNames.get(task.assignee_id) ?? shortId(task.assignee_id) : "미배정"}</span></div>}
              <div className="queue-updated"><span>{formatDate(task.updated_at)}</span></div>
              <StatusBadge status={task.status} /><ArrowRight className="row-arrow" size={18} />
            </Link></div>;
          })}</div>}
        {tasks.isFetchNextPageError && <div className="inline-alert inline-alert-danger queue-page-error" role="alert">다음 검토 작업을 불러오지 못했습니다. 현재 목록은 그대로 유지됩니다.</div>}
        {tasks.hasNextPage && <div className="queue-more"><button className="button button-secondary" type="button" disabled={tasks.isFetchingNextPage} onClick={() => { void tasks.fetchNextPage(); }}>{tasks.isFetchingNextPage ? "더 불러오는 중…" : "검토 작업 더 보기"}</button></div>}
      </div>
    </Card>
  </div>;
}
