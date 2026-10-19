import { ArrowLeft, CheckCircle2, FileCheck2, FileImage, LockKeyhole, MessageSquareWarning, ShieldAlert, ThumbsDown, ThumbsUp, UserCheck } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError, api } from "../api/client";
import type { CaseDetail, ReviewTaskDetail } from "../api/contracts";
import { useAuth } from "../auth/AuthProvider";
import { AccessibleDialog } from "../components/AccessibleDialog";
import { Card, DefinitionList, Loading, Notice, PageHeader, formatDate, friendlyError, shortId, textValue } from "../components/Ui";
import { StatusBadge } from "../components/StatusBadge";
import { formatCommerceMoney, readSyntheticCommerceContext } from "../commerce/syntheticCommerceContext";
import { demoProductDisplayName } from "../demo/productScenarioCatalog";
import { EvidencePreview, type EvidencePreviewStatus } from "../evidence/EvidencePreview";
import { businessLabel, fieldLabel, inquiryTitle } from "../presentation/businessLabels";
import { qualificationPresentation } from "../presentation/reviewPresentation";
import { reportWaitDelay } from "../report/reportWait";
import { assessQuickReview, quickResolveInput, reviewBasisOptions, type BasisOption, type QuickReviewVerdict } from "../review/quickReview";

const decisions = ["APPROVE_REFUND", "APPROVE_EXCHANGE", "APPROVE_RESHIPMENT", "APPROVE_REPAIR", "REJECT_REQUEST", "PROVIDE_INFORMATION", "NO_ACTION"];
const reasons = ["POLICY_CONDITION_MET", "POLICY_CONDITION_NOT_MET", "POLICY_EXCEPTION", "EVIDENCE_SUFFICIENT", "EVIDENCE_INSUFFICIENT", "CUSTOMER_INFORMATION_ONLY", "OTHER"];

export function ReviewDetailPage() {
  const { taskId = "" } = useParams();
  const { user, hasRole } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [awaitingReportCaseId, setAwaitingReportCaseId] = useState<string | null>(null);
  const [reportPollAttempt, setReportPollAttempt] = useState(0);
  const [pendingQuickVerdict, setPendingQuickVerdict] = useState<QuickReviewVerdict | null>(null);
  const [quickOutcomeUnknown, setQuickOutcomeUnknown] = useState(false);
  const [checkingQuickOutcome, setCheckingQuickOutcome] = useState(false);
  const [quickStatus, setQuickStatus] = useState<string | null>(null);
  const [evidenceStatuses, setEvidenceStatuses] = useState<Record<string, EvidencePreviewStatus>>({});
  const handleEvidenceStatus = useCallback((evidenceId: string, status: EvidencePreviewStatus) => {
    setEvidenceStatuses((current) => current[evidenceId] === status
      ? current
      : { ...current, [evidenceId]: status });
  }, []);
  const detail = useQuery({ queryKey: ["review", taskId], queryFn: () => api.getReviewTask(taskId), enabled: Boolean(taskId) });
  const reviewCase = useQuery({
    queryKey: ["case", detail.data?.task.case_id],
    queryFn: () => api.getCase(detail.data!.task.case_id),
    enabled: Boolean(detail.data?.task.case_id),
    retry: false,
  });
  const report = useQuery({
    queryKey: ["report", awaitingReportCaseId],
    queryFn: () => api.getReport(awaitingReportCaseId as string),
    enabled: Boolean(awaitingReportCaseId),
    retry: false,
  });
  const reportNotReady = report.error instanceof ApiError && report.error.status === 404;
  const nextReportDelay = reportWaitDelay(reportPollAttempt);
  const refetchReport = report.refetch;
  const reportWaitStopped = Boolean(
    awaitingReportCaseId
    && report.isError
    && !report.isFetching
    && (!reportNotReady || nextReportDelay === null),
  );

  useEffect(() => {
    if (awaitingReportCaseId && report.data) navigate(`/cases/${awaitingReportCaseId}/report`, { replace: true });
  }, [awaitingReportCaseId, navigate, report.data]);

  useEffect(() => {
    if (!awaitingReportCaseId || report.data || report.isFetching || !reportNotReady || nextReportDelay === null) return;
    const timeout = window.setTimeout(() => {
      setReportPollAttempt((current) => current + 1);
      void refetchReport();
    }, nextReportDelay);
    return () => window.clearTimeout(timeout);
  }, [awaitingReportCaseId, nextReportDelay, refetchReport, report.data, report.errorUpdatedAt, report.isFetching, reportNotReady]);

  const action = useMutation({
    mutationFn: ({ name, body }: { name: string; body: Record<string, unknown> }) => api.reviewAction(taskId, name, body),
    onSuccess: async () => {
      setActionError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["review", taskId] }),
        queryClient.invalidateQueries({ queryKey: ["reviews"] }),
        detail.data?.task.case_id ? queryClient.invalidateQueries({ queryKey: ["resolution", detail.data.task.case_id] }) : Promise.resolve(),
      ]);
    },
    onError: async (cause) => {
      if (cause instanceof ApiError && cause.status === 409) {
        await queryClient.invalidateQueries({ queryKey: ["review", taskId] });
        setActionError("다른 담당자가 먼저 작업을 변경했습니다. 최신 내용을 불러왔으니 다시 확인해 주세요.");
      } else setActionError(friendlyError(cause));
    },
  });

  const basisOptions = useMemo<BasisOption[]>(() => detail.data ? reviewBasisOptions(detail.data) : [], [detail.data]);
  const quickReview = useMemo(() => detail.data ? assessQuickReview(detail.data) : null, [detail.data]);
  const quickConfirmationInput = useMemo(() => (
    pendingQuickVerdict && quickReview && detail.data
      ? quickResolveInput(quickReview, pendingQuickVerdict, detail.data.task.version)
      : null
  ), [detail.data, pendingQuickVerdict, quickReview]);
  const quickAction = useMutation({
    mutationFn: async (verdict: QuickReviewVerdict) => {
      if (!detail.data || !quickReview) throw new Error("빠른 검토 준비도를 확인할 수 없습니다.");
      const currentTask = detail.data.task;
      const requiresAdmin = ["SAFETY_REVIEW", "MANAGER_REVIEW", "POLICY_EXCEPTION_REVIEW"].includes(currentTask.task_type);
      const mayClaim = (!requiresAdmin || hasRole("ADMIN"))
        && (currentTask.status === "PENDING" || (currentTask.status === "ESCALATED" && hasRole("ADMIN")));
      let expectedVersion = currentTask.version;
      if (mayClaim) {
        const claimed = await api.reviewAction(taskId, "claim", { expected_version: expectedVersion });
        expectedVersion = claimed.task.version;
      }
      return api.resolveReview(taskId, quickResolveInput(quickReview, verdict, expectedVersion));
    },
    onSuccess: async () => {
      const caseId = detail.data?.task.case_id;
      setActionError(null);
      setActionNotice(null);
      setPendingQuickVerdict(null);
      setQuickOutcomeUnknown(false);
      setQuickStatus(null);
      if (caseId) {
        setReportPollAttempt(0);
        setAwaitingReportCaseId(caseId);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["review", taskId] }),
        queryClient.invalidateQueries({ queryKey: ["reviews"] }),
        caseId ? queryClient.invalidateQueries({ queryKey: ["resolution", caseId] }) : Promise.resolve(),
        caseId ? queryClient.invalidateQueries({ queryKey: ["report", caseId] }) : Promise.resolve(),
      ]);
    },
    onError: async (cause) => {
      setQuickOutcomeUnknown(true);
      setQuickStatus("요청 응답만으로는 결정 기록 여부를 확정할 수 없습니다. 최신 검토 상태를 확인하고 있습니다.");
      await reconcileQuickOutcome(cause);
    },
  });

  async function reconcileQuickOutcome(cause?: unknown) {
    setCheckingQuickOutcome(true);
    const latest = await detail.refetch();
    setCheckingQuickOutcome(false);
    if (latest.error || !latest.data) {
      setQuickOutcomeUnknown(true);
      setQuickStatus("최신 상태를 확인하지 못했습니다. 결정을 다시 보내지 말고, 연결이 복구된 뒤 최신 상태를 다시 확인해 주세요.");
      return;
    }
    const latestTask = latest.data.task;
    if (latestTask.status === "RESOLVED" && latest.data.decision) {
      const caseId = latestTask.case_id;
      setPendingQuickVerdict(null);
      setQuickOutcomeUnknown(false);
      setQuickStatus(null);
      setActionError(null);
      setActionNotice("응답은 명확하지 않았지만 최신 검토 상태에서 최종 결정 기록을 확인했습니다. 결정을 다시 보내지 않았습니다.");
      setReportPollAttempt(0);
      setAwaitingReportCaseId(caseId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["reviews"] }),
        queryClient.invalidateQueries({ queryKey: ["resolution", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["report", caseId] }),
      ]);
      return;
    }
    if (latestTask.status === "RESOLVED") {
      setQuickOutcomeUnknown(true);
      setQuickStatus("작업은 완료 상태지만 결정 기록을 아직 확인할 수 없습니다. 재전송하지 말고 최신 상태를 다시 확인해 주세요.");
      return;
    }

    setQuickOutcomeUnknown(false);
    const canContinueClaim = latestTask.status === "CLAIMED" && latestTask.current_assignee_id === user?.user_id;
    if (cause instanceof ApiError && cause.status === 409 && !canContinueClaim) {
      setPendingQuickVerdict(null);
      setQuickStatus(null);
      setActionError("다른 담당자가 먼저 작업을 변경했습니다. 최신 내용을 불러왔으니 다시 확인해 주세요.");
      return;
    }
    setActionError(null);
    setQuickStatus(cause
      ? `최신 상태에서 결정이 기록되지 않은 것을 확인했습니다. ${friendlyError(cause)} 내용을 다시 확인한 뒤에만 재시도해 주세요.`
      : "최신 상태에서 결정이 기록되지 않은 것을 확인했습니다. 내용을 다시 확인한 뒤 확정할 수 있습니다.");
  }

  function openQuickConfirmation(verdict: QuickReviewVerdict) {
    setActionError(null);
    setActionNotice(null);
    if (!quickOutcomeUnknown) setQuickStatus(null);
    setPendingQuickVerdict(verdict);
  }

  function closeQuickConfirmation() {
    if (quickAction.isPending || checkingQuickOutcome) return;
    setPendingQuickVerdict(null);
    if (!quickOutcomeUnknown) setQuickStatus(null);
  }

  function retryReport() {
    setReportPollAttempt(0);
    void report.refetch();
  }

  if (detail.isLoading && !detail.data) return <div className="page"><Loading label="검토 패킷의 무결성을 확인하는 중" /></div>;
  if (!detail.data) return <div className="page"><div className="error-panel" role="alert">{friendlyError(detail.error)}</div></div>;
  const { task, packet } = detail.data;
  const commerce = readSyntheticCommerceContext(reviewCase.data?.attributes);
  const productName = commerce?.order.productDisplayName
    ?? (reviewCase.data ? demoProductDisplayName(reviewCase.data.product_ref) : undefined)
    ?? (reviewCase.isLoading ? "상품명 확인 중" : "상품명 정보 없음");
  const adminOnlyTask = ["SAFETY_REVIEW", "MANAGER_REVIEW", "POLICY_EXCEPTION_REVIEW"].includes(task.task_type);
  const adminOnlyBlocked = adminOnlyTask && !hasRole("ADMIN");
  const reviewQueueLabel = hasRole("ADMIN") ? "검토 대기함" : "내 문의 처리 현황";
  const canClaim = !adminOnlyBlocked && (task.status === "PENDING" || (task.status === "ESCALATED" && hasRole("ADMIN")));
  const canAct = task.status === "CLAIMED" && task.current_assignee_id === user?.user_id;
  const requiredImageIds = reviewCase.data?.evidence.filter((item) => item.evidence_type === "IMAGE").map((item) => item.evidence_id) ?? [];
  const evidenceReady = requiredImageIds.every((evidenceId) => evidenceStatuses[evidenceId] === "READY");
  const evidenceFailed = requiredImageIds.some((evidenceId) => evidenceStatuses[evidenceId] === "FAILED");
  const caseReadyForDecision = Boolean(reviewCase.data) && !reviewCase.isError && evidenceReady;
  const decisionBlockReason = !reviewCase.data || reviewCase.isError
    ? "문의와 첨부 사진을 정상적으로 불러온 뒤에만 최종 결정을 기록할 수 있습니다."
    : evidenceFailed
      ? "확인할 수 없는 첨부 사진이 있습니다. 사진을 다시 불러와 모두 확인한 뒤 최종 결정을 기록해 주세요."
      : !evidenceReady
        ? "첨부 사진을 확인하는 중입니다. 모든 사진이 표시된 뒤 최종 결정을 기록할 수 있습니다."
        : null;
  const canQuickReview = Boolean(quickReview?.eligible) && (canClaim || canAct) && !adminOnlyBlocked;

  function simpleAction(name: string, body: Record<string, unknown>) {
    setActionError(null);
    action.mutate({ name, body: { expected_version: task.version, ...body } });
  }

  function requestEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    simpleAction("request-additional-evidence", {
      reason_codes: [String(data.get("reason"))], instructions: String(data.get("instructions")), rationale: String(data.get("rationale") || "") || null,
    });
  }

  function resolve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!caseReadyForDecision) {
      setActionError(decisionBlockReason ?? "문의와 첨부 사진을 확인해 주세요.");
      return;
    }
    const data = new FormData(event.currentTarget);
    const selected = data.getAll("basis").map((raw) => basisOptions[Number(raw)]).filter((option): option is BasisOption => option !== undefined);
    if (!selected.length) {
      setActionError("결정 근거를 하나 이상 선택해 주세요.");
      return;
    }
    if (!selected.some((option) => option.type === "POLICY_RULE_RESULT" || option.type === "POLICY_CITATION")) {
      setActionError("정책 규칙 또는 인용 근거를 하나 이상 선택해 주세요.");
      return;
    }
    simpleAction("resolve", {
      decision: String(data.get("decision")), reason_codes: [String(data.get("reason"))],
      rationale: String(data.get("rationale")), basis: selected.map(({ type, reference_id }) => ({ type, reference_id })),
    });
  }

  return <><div className="page review-detail-page">
    <PageHeader eyebrow={`최종 결정 검토 · ${shortId(task.id)}`} title={reviewCase.data ? `${inquiryTitle(reviewCase.data.requested_action)} 검토` : "문의 검토"} description="사진과 요약을 확인하고 처리 여부를 선택하세요."
      actions={<><Link className="button button-ghost" to="/reviews"><ArrowLeft size={18} />{reviewQueueLabel}</Link><StatusBadge status={task.status} /></>} />
    {actionError && <div className="inline-alert inline-alert-danger" role="alert">{actionError}</div>}
    {actionNotice && <Notice tone="success" title="최신 상태 확인 완료"><span>{actionNotice}</span></Notice>}
    {adminOnlyBlocked && <Notice tone="danger" title="관리자 전용 검토"><span>안전·관리자·정책 예외 검토의 최종 결정은 관리자만 기록할 수 있습니다. 담당자는 근거를 확인한 뒤 관리자에게 이관할 수 있습니다.</span></Notice>}
    <div className="review-layout">
      <div className="review-body">
        <Card actions={<span className="integrity-badge"><LockKeyhole size={14} />변경 방지 기록</span>}>
          <section className="review-summary-section"><h3>고객 첨부 사진</h3>{reviewCase.isLoading ? <Loading label="첨부 사진을 불러오는 중" /> : reviewCase.isError && !reviewCase.data ? <div className="inline-alert inline-alert-danger review-evidence-load-error" role="alert"><span>문의와 첨부 사진을 불러오지 못했습니다. 내용을 확인할 수 없어 최종 결정은 잠시 잠겼습니다.</span><button className="button button-secondary" type="button" disabled={reviewCase.isFetching} onClick={() => { void reviewCase.refetch(); }}>{reviewCase.isFetching ? "다시 불러오는 중…" : "문의와 사진 다시 불러오기"}</button></div> : reviewCase.data?.evidence.length ? <><div className="evidence-grid">{reviewCase.data.evidence.map((evidence) => <EvidencePreview compact caseId={task.case_id} evidence={evidence} key={evidence.evidence_id} onStatusChange={handleEvidenceStatus} />)}</div>{!evidenceReady && <Notice tone={evidenceFailed ? "danger" : "warning"} title={evidenceFailed ? "확인할 수 없는 사진이 있습니다" : "사진 확인 중"}><span>{decisionBlockReason}</span></Notice>}</> : <p className="muted-copy">첨부 사진이 없습니다.</p>}</section>

          <section className="review-summary-section inquiry-focus"><h3>문의 내용 요약</h3><p>{detail.data.inquiry_summary?.trim() || "저장된 요약이 없습니다. 아래 원문을 확인해 주세요."}</p></section>

        </Card>
      </div>
      <aside className="decision-panel">
        <Card title="검토 작업">
          {awaitingReportCaseId ? <>
            {!reportWaitStopped && <Notice tone="success" title="결정 기록 완료 · 문서 생성 중"><span>최종 결정은 이미 기록되었습니다. 검토 문서가 준비되는 동안 제한된 횟수만 자동으로 확인합니다.</span></Notice>}
            {reportWaitStopped && <Notice tone="warning" title="결정은 기록됐고 문서는 아직 생성 중입니다"><div className="report-wait-actions"><span>결정을 다시 누르지 마세요. 잠시 후 문서만 다시 확인하거나 문의 화면으로 돌아갈 수 있습니다.</span><button className="button button-secondary" type="button" disabled={report.isFetching} onClick={retryReport}>{report.isFetching ? "확인 중…" : "문서 다시 확인"}</button><Link className="button button-ghost" to={`/cases/${task.case_id}`}>문의 화면으로</Link></div></Notice>}
          </> : task.status === "RESOLVED" ? <><Notice tone="success" title="결정이 고정되었습니다"><span>기존 결정은 변경하지 않습니다. 다른 결정이 발견되면 자동 대체하지 않고 수동 후속 조치로 전환됩니다.</span></Notice><DefinitionList items={Object.entries(detail.data.decision ?? {}).slice(0, 6).map(([label, value]) => ({ label: fieldLabel(label), value: Array.isArray(value) ? value.map(businessLabel).join(", ") : businessLabel(value) }))} /><Link className="button button-primary full-button" to={`/cases/${task.case_id}/report`}><FileCheck2 size={18} />최종 검토 문서 보기</Link><Link className="button button-ghost full-button" to={`/cases/${task.case_id}`}>처리 결과 확인</Link></> : <>
            {canQuickReview && quickReview && <QuickReviewPanel assessment={quickReview} pending={quickAction.isPending || Boolean(awaitingReportCaseId)} onVerdict={openQuickConfirmation} />}
            {canClaim && !canQuickReview && <button className="button button-primary full-button" disabled={action.isPending} type="button" onClick={() => simpleAction("claim", {})}><UserCheck size={18} />내가 검토하기</button>}
            {task.status === "WAITING_FOR_EVIDENCE" && <button className="button button-primary full-button" disabled={action.isPending} type="button" onClick={() => simpleAction("resume", { rationale: "추가 자료가 제출되어 검토를 재개합니다." })}>검토 재개</button>}
            {canAct && !adminOnlyBlocked && <details className="manual-review-details"><summary>상세 결정 또는 자료 요청</summary><DecisionForms basisOptions={basisOptions} decisionBlockReason={decisionBlockReason} onEvidence={requestEvidence} onResolve={resolve} pending={action.isPending} /></details>}
            {canClaim && canQuickReview && <details className="manual-review-details"><summary>빠른 검토 대신 상세 검토</summary><button className="button button-ghost full-button" disabled={action.isPending || quickAction.isPending} type="button" onClick={() => simpleAction("claim", {})}><UserCheck size={18} />상세 검토 시작</button></details>}
            {quickReview && !quickReview.eligible && task.status !== "WAITING_FOR_EVIDENCE" && <Notice tone="warning" title="빠른 검토 보류"><span>{quickReview.blockers.join(" ")}</span></Notice>}
            {canAct && <div className="minor-actions">
              <button className="button button-ghost" type="button" disabled={action.isPending} onClick={() => simpleAction("escalate", { reason_codes: [task.task_type === "SAFETY_REVIEW" ? "SAFETY_RISK" : "INSUFFICIENT_AUTHORITY"], rationale: "권한과 위험 수준을 확인하기 위해 관리자 검토가 필요합니다." })}><ShieldAlert size={17} />관리자 이관</button>
              <button className="button button-ghost" type="button" disabled={action.isPending} onClick={() => simpleAction("release", { reason_code: "WORK_QUEUE_RETURN" })}>작업 반환</button>
            </div>}
            {!canClaim && !canAct && task.status !== "WAITING_FOR_EVIDENCE" && <Notice title="현재 작업 상태"><span>{task.current_assignee_id ? "다른 담당자가 검토 중입니다." : "관리자 작업을 기다리고 있습니다."}</span></Notice>}
          </>}
        </Card>
      </aside>
    </div>
    <section className="review-bottom-details" aria-label="추가 정보">
      <details className="review-technical-details"><summary>고객 정보</summary>
        {commerce ? <DefinitionList items={[
          { label: "고객", value: commerce.customer.displayName },
          { label: "연락처", value: commerce.customer.phoneMasked },
          { label: "수령인", value: commerce.delivery.recipient },
          { label: "배송지", value: `${commerce.delivery.addressLine1} ${commerce.delivery.addressLine2}` },
        ]} /> : <p className="muted-copy">고객 정보가 없습니다.</p>}
        {commerce && <p className="muted-copy">가상 주문의 고객 정보입니다.</p>}
      </details>
      <details className="review-technical-details"><summary>상품·주문 정보</summary>
          <p className="review-product-caption">{productName} · 상품코드 {reviewCase.data?.product_ref ?? "확인 중"}<br />{commerce ? `결제 금액 ${formatCommerceMoney(commerce.order.paidAmount, commerce.order.currency)} · 가상 주문` : "금액 정보 없음"}</p>
        <DefinitionList items={[
          { label: "주문 번호", value: reviewCase.data?.order_ref ?? "정보 없음" },
          { label: "고객 요청", value: businessLabel(reviewCase.data?.requested_action) },
        ]} />
      </details>
          <details className="review-technical-details" open={!detail.data.inquiry_summary?.trim()}><summary>문의 원문 보기</summary><p className="inquiry-original">{reviewCase.data?.customer_message ?? "문의를 불러오는 중입니다."}</p></details>
          <details className="review-technical-details"><summary>정책 근거·분석 상세 보기</summary>
          <Link className="button button-ghost" to={`/cases/${task.case_id}?details=1`}>문의 처리 단계 보기</Link>
          <PacketSummary packet={packet} />
          {detail.data.grounded_explanation && <div className="explanation-box"><MessageSquareWarning size={19} /><div><strong>정책 근거 확인 요약</strong><span>담당자 판단 참고</span><p>{textValue(detail.data.grounded_explanation.explanation ?? detail.data.grounded_explanation.summary ?? detail.data.grounded_explanation)}</p></div></div>}
          <PolicyBasis citations={detail.data.citation_items} />
          <details className="review-technical-details"><summary>정책 유사도 비교 보기</summary><PolicySimilarity evidence={detail.data.policy_similarity} /></details>
          <details className="review-technical-details"><summary>기술 정보 보기</summary><DefinitionList items={[
            { label: "정책 평가 번호", value: shortId(task.policy_evaluation_run_id) },
            { label: "검토 기준 버전", value: `${task.mapping_rule_name} · ${task.mapping_rule_version}` },
            { label: "작업 유형", value: businessLabel(task.task_type) },
            { label: "우선순위", value: businessLabel(task.priority) },
            { label: "생성", value: formatDate(task.created_at) },
          ]} /><p className="muted-copy">작업 기록 {detail.data.actions.length}건 · 정책 규칙 결과 {detail.data.rule_results.length}건</p></details>
          </details>
    </section>
  </div>
    {pendingQuickVerdict && quickReview && quickConfirmationInput && <QuickDecisionConfirmation
      assessment={quickReview}
      caseData={reviewCase.data}
      caseError={reviewCase.error}
      caseLoading={reviewCase.isLoading}
      checkingOutcome={checkingQuickOutcome}
      detail={detail.data}
      evidenceFailed={evidenceFailed}
      evidenceReady={evidenceReady}
      input={quickConfirmationInput}
      outcomeUnknown={quickOutcomeUnknown}
      pending={quickAction.isPending}
      status={quickStatus}
      verdict={pendingQuickVerdict}
      onCancel={closeQuickConfirmation}
      onConfirm={() => quickAction.mutate(pendingQuickVerdict)}
      onRecheck={() => { void reconcileQuickOutcome(); }}
      onRetryCase={() => { void reviewCase.refetch(); }}
    />}
  </>;
}

function PacketSummary({ packet }: { packet: Record<string, unknown> }) {
  const recommendation = packet.policy_summary_status ?? packet.recommendation ?? packet.policy_recommendation ?? packet.summary_status;
  const qualification = packet.qualification_snapshot ?? packet.input_qualification ?? packet.model_qualification;
  const qualificationItems = qualificationPresentation(qualification);
  return <div className="packet-highlight"><div className="policy-recommendation"><span>정책 권고</span><strong>{businessLabel(recommendation)}</strong><small>정책은 참고 기준이며 최종 결정은 담당자가 기록합니다.</small></div><div><span>분석 확인 상태</span><ul className="qualification-list">{qualificationItems.map((item) => <li key={item.label}><span>{item.label}</span><strong className={`qualification-${item.tone}`}>{item.status}</strong></li>)}</ul></div></div>;
}

function PolicyBasis({ citations }: { citations: Array<Record<string, unknown>> }) {
  return <section className="review-summary-section"><h3>적절하다고 본 정책 근거</h3>{citations.length ? <div className="policy-evidence-list">{citations.slice(0, 3).map((item, index) => <article key={String(item.id ?? item.citation_id ?? index)}><span className="policy-evidence-rank">{index + 1}</span><div><strong>{textValue(item.title ?? item.document_id)}</strong><small>{textValue(item.section_path ?? item.policy_clause_id)}</small><p>{textValue(item.text ?? "조항 본문은 기존 실행에 저장되지 않았습니다.")}</p></div></article>)}</div> : <p className="muted-copy">연결된 정책 인용이 없습니다. 최종 결정 전에 정책 검색 상태를 확인해 주세요.</p>}</section>;
}

function PolicySimilarity({ evidence }: { evidence: ReviewTaskDetail["policy_similarity"] }) {
  const nearest = evidence.filter((item) => item.group === "NEAREST").sort((left, right) => left.rank - right.rank).slice(0, 3);
  const least = evidence.filter((item) => item.group === "LEAST").sort((left, right) => left.rank - right.rank).slice(0, 3);
  if (!evidence.length) return <section className="review-summary-section"><h3>유사도 비교</h3><Notice tone="warning" title="기존 분석 실행"><span>이 문의의 기존 검색 실행에는 코사인 비교 근거가 저장되지 않았습니다. 분석을 다시 실행하면 가장 가까운 정책 3개와 가장 부적합한 정책 3개가 표시됩니다.</span></Notice></section>;
  return <section className="review-summary-section"><h3>정책 유사도 비교</h3><p className="muted-copy">참고 임계값은 화면 설명용이며 승인·거절을 자동 결정하지 않습니다.</p><div className="similarity-columns"><SimilarityList title="임계값에 가장 가까운 정책 3개" items={nearest} least={false} /><SimilarityList title="가장 부적합한 정책 3개" items={least} least /></div></section>;
}

function SimilarityList({ title, items, least }: { title: string; items: ReviewTaskDetail["policy_similarity"]; least: boolean }) {
  return <div className={least ? "similarity-group similarity-group-least" : "similarity-group"}><h4>{title}</h4>{items.map((item) => <article key={`${item.group}-${item.rank}`}><div><strong>{item.rank}. {item.title}</strong><span>코사인 유사도 {item.cosine_similarity.toFixed(3)} · 참고선 {item.reference_threshold.toFixed(2)}</span></div><p>{item.text}</p>{least && <small>부적격 이유: 비교 후보 중 유사도가 {item.rank}번째로 낮고 참고선보다 {Math.abs(item.reference_threshold - item.cosine_similarity).toFixed(3)}만큼 멀어, 현재 문의의 정책 적용 맥락과 거리가 큽니다.</small>}</article>)}</div>;
}

function QuickDecisionConfirmation({
  assessment,
  caseData,
  caseError,
  caseLoading,
  checkingOutcome,
  detail,
  evidenceFailed,
  evidenceReady,
  input,
  outcomeUnknown,
  pending,
  status,
  verdict,
  onCancel,
  onConfirm,
  onRecheck,
  onRetryCase,
}: {
  assessment: ReturnType<typeof assessQuickReview>;
  caseData: CaseDetail | undefined;
  caseError: Error | null;
  caseLoading: boolean;
  checkingOutcome: boolean;
  detail: ReviewTaskDetail;
  evidenceFailed: boolean;
  evidenceReady: boolean;
  input: ReturnType<typeof quickResolveInput>;
  outcomeUnknown: boolean;
  pending: boolean;
  status: string | null;
  verdict: QuickReviewVerdict;
  onCancel(): void;
  onConfirm(): void;
  onRecheck(): void;
  onRetryCase(): void;
}) {
  const commerce = readSyntheticCommerceContext(caseData?.attributes);
  const [dialogEvidenceStatuses, setDialogEvidenceStatuses] = useState<Record<string, EvidencePreviewStatus>>({});
  const handleDialogEvidenceStatus = useCallback((evidenceId: string, evidenceStatus: EvidencePreviewStatus) => {
    setDialogEvidenceStatuses((current) => current[evidenceId] === evidenceStatus
      ? current
      : { ...current, [evidenceId]: evidenceStatus });
  }, []);
  const dialogImageIds = caseData?.evidence.filter((item) => item.evidence_type === "IMAGE").map((item) => item.evidence_id) ?? [];
  const dialogEvidenceReady = dialogImageIds.every((evidenceId) => dialogEvidenceStatuses[evidenceId] === "READY");
  const dialogEvidenceFailed = dialogImageIds.some((evidenceId) => dialogEvidenceStatuses[evidenceId] === "FAILED");
  const allEvidenceReady = evidenceReady && dialogEvidenceReady;
  const anyEvidenceFailed = evidenceFailed || dialogEvidenceFailed;
  const basis = input.basis.map((selected) => assessment.basis.find(
    (option) => option.type === selected.type && option.reference_id === selected.reference_id,
  ));
  const confirmDisabled = pending || checkingOutcome || outcomeUnknown || !caseData || !allEvidenceReady;

  return <AccessibleDialog
    open
    title={`${businessLabel(input.decision)}을 최종 기록할까요?`}
    description="첫 선택만으로는 아무 결정도 기록되지 않았습니다. 아래 문의·증거·정책과 정확한 결정 내용을 확인한 뒤 최종 기록 버튼을 눌러야 반영됩니다."
    closeDisabled={pending || checkingOutcome}
    onClose={onCancel}
    footer={<>
      <button className="button button-secondary" type="button" disabled={pending || checkingOutcome} onClick={onCancel}>취소</button>
      {outcomeUnknown && <button className="button button-secondary" type="button" disabled={checkingOutcome} onClick={onRecheck}>{checkingOutcome ? "최신 상태 확인 중…" : "최신 상태 다시 확인"}</button>}
      <button className={`button ${verdict === "DENY" ? "button-danger" : "button-primary"}`} type="button" disabled={confirmDisabled} onClick={onConfirm}>
        <LockKeyhole aria-hidden="true" size={17} />{pending ? "결정 기록 중…" : `${businessLabel(input.decision)} 최종 결정 기록`}
      </button>
    </>}
  >
    {status && <div className={`inline-alert ${outcomeUnknown ? "inline-alert-danger" : ""}`} role={outcomeUnknown ? "alert" : "status"}>{status}</div>}
    <section className="decision-confirm-section" aria-labelledby="decision-case-context">
      <div className="decision-confirm-heading"><div><p className="eyebrow">1 · 문의와 주문</p><h3 id="decision-case-context">고객이 요청한 내용</h3></div>{caseData && <StatusBadge status={caseData.status} />}</div>
      {caseLoading && <Loading label="문의와 증거를 불러오는 중" />}
      {!caseLoading && caseError && !caseData && <div className="dialog-load-error" role="alert"><span>문의와 증거를 불러오지 못했습니다. 이 상태에서는 결정을 기록할 수 없습니다.</span><button className="button button-secondary" type="button" onClick={onRetryCase}>다시 불러오기</button></div>}
      {caseData && <>
        <DefinitionList items={[
          { label: "문의 번호", value: shortId(caseData.case_id) },
          { label: "주문 참조", value: caseData.order_ref },
          { label: "상품", value: commerce?.order.productDisplayName ?? demoProductDisplayName(caseData.product_ref) ?? "등록 상품" },
          { label: "상품 참조", value: caseData.product_ref },
          { label: "고객 요청", value: businessLabel(caseData.requested_action) },
          ...(commerce ? [
            { label: "주문 수량", value: `${commerce.order.quantity}개` },
            { label: "결제 금액", value: formatCommerceMoney(commerce.order.paidAmount, commerce.order.currency) },
            { label: "주문 일시", value: formatDate(commerce.order.orderedAt) },
          ] : []),
        ]} />
        <div className="decision-inquiry"><strong>고객 문의 원문</strong><blockquote>{caseData.customer_message}</blockquote></div>
        <div className="decision-evidence-heading"><strong>제출 증거</strong><span>{caseData.evidence.length}개</span></div>
        {caseData.evidence.length
          ? <><div className="decision-evidence-grid">{caseData.evidence.map((evidence) => <EvidencePreview key={evidence.evidence_id} caseId={caseData.case_id} evidence={evidence} onStatusChange={handleDialogEvidenceStatus} />)}</div>{!allEvidenceReady && <Notice tone={anyEvidenceFailed ? "danger" : "warning"} title={anyEvidenceFailed ? "사진 확인 실패 · 최종 결정 잠김" : "사진 확인 중 · 최종 결정 잠김"}><span>{anyEvidenceFailed ? "표시하지 못한 사진을 다시 불러온 뒤 모든 사진이 정상적으로 보여야 결정할 수 있습니다." : "모든 첨부 사진이 정상적으로 표시될 때까지 최종 기록 버튼을 사용할 수 없습니다."}</span></Notice>}</>
          : <Notice tone="warning" title="제출된 증거가 없습니다"><span>문의 원문과 정책 근거만으로 결정 가능한지 다시 확인하세요.</span></Notice>}
      </>}
    </section>

    <section className="decision-confirm-section" aria-labelledby="decision-policy-context">
      <p className="eyebrow">2 · 정책과 분석 범위</p>
      <h3 id="decision-policy-context">정책 권고와 자격 상태</h3>
      <PacketSummary packet={detail.packet} />
      <p className="decision-boundary-copy">정책과 모델 출력은 판단 자료입니다. 아래 최종 결정은 로그인한 담당자의 명시적 확인으로만 생성됩니다.</p>
    </section>

    <section className="decision-confirm-section decision-final-record" aria-labelledby="decision-exact-record">
      <p className="eyebrow">3 · 기록될 내용</p>
      <h3 id="decision-exact-record">정확한 최종 결정</h3>
      <DefinitionList items={[
        { label: "최종 결정", value: <strong>{businessLabel(input.decision)}</strong> },
        { label: "결정 사유", value: input.reason_codes.map(businessLabel).join(", ") },
        { label: "판단 근거 설명", value: input.rationale },
        { label: "정책 근거", value: basis.map((option, index) => option?.label ?? `${input.basis[index]?.type ?? "정책 근거"} · ${input.basis[index]?.reference_id ?? "확인 필요"}`).join(" / ") },
      ]} />
      <Notice tone="warning" title="확정 후에는 변경할 수 없습니다"><span>실제 환불·수리·메일 발송 같은 외부 조치는 실행하지 않습니다. 다른 판단이 필요하면 기존 결정을 덮어쓰지 않고 별도 후속 검토로 처리합니다.</span></Notice>
    </section>
  </AccessibleDialog>;
}

function QuickReviewPanel({ assessment, pending, onVerdict }: {
  assessment: ReturnType<typeof assessQuickReview>;
  pending: boolean;
  onVerdict(verdict: QuickReviewVerdict): void;
}) {
  const percent = Math.round(assessment.score * 100);
  const threshold = Math.round(assessment.threshold * 100);
  return <section className="quick-review-panel" aria-labelledby="quick-review-title" data-testid="quick-review-panel">
    <div className="quick-review-head"><div><p className="eyebrow">빠른 검토</p><h3 id="quick-review-title">허용 여부만 선택하세요</h3></div><span className="readiness-score">준비도 {percent}%</span></div>
    <div className="review-threshold" aria-label={`빠른 검토 threshold ${threshold}%`}><span>Threshold · 빠른 검토 기준</span><strong>{threshold}<small>%</small></strong></div>
    <small>모델 정확도가 아닌 정책·근거·입력 준비도입니다.</small>
    <div className="quick-verdict-actions">
      <button className="button quick-allow" type="button" disabled={pending || !assessment.allowDecision} onClick={() => onVerdict("ALLOW")}><ThumbsUp size={20} /><span><strong>{assessment.allowLabel}</strong><small>내용 확인 후 최종 확정</small></span></button>
      <button className="button quick-deny" type="button" disabled={pending} onClick={() => onVerdict("DENY")}><ThumbsDown size={20} /><span><strong>비허용</strong><small>내용 확인 후 최종 확정</small></span></button>
    </div>
    {!assessment.allowDecision && <p className="quick-review-note">정책 효과에서 처리 유형이 하나로 정해지지 않아 허용은 상세 검토가 필요합니다. 비허용은 확인창을 거쳐 기록합니다.</p>}
    <p className="quick-review-warning"><LockKeyhole size={14} />선택 후 확인창에서 최종 확정합니다.</p>
  </section>;
}

function DecisionForms({ basisOptions, decisionBlockReason, onEvidence, onResolve, pending }: {
  basisOptions: BasisOption[];
  decisionBlockReason: string | null;
  onEvidence(event: FormEvent<HTMLFormElement>): void;
  onResolve(event: FormEvent<HTMLFormElement>): void;
  pending: boolean;
}) {
  const [mode, setMode] = useState<"resolve" | "evidence">("resolve");
  return <div className="decision-forms">
    <div className="segmented"><button type="button" className={mode === "resolve" ? "active" : ""} onClick={() => setMode("resolve")}>결정</button><button type="button" className={mode === "evidence" ? "active" : ""} onClick={() => setMode("evidence")}>자료 요청</button></div>
    {mode === "resolve" ? <form onSubmit={onResolve} data-testid="resolve-form">
      {decisionBlockReason && <Notice tone="danger" title="문의와 사진 확인 필요"><span>{decisionBlockReason}</span></Notice>}
      <label>최종 결정<select name="decision" required>{decisions.map((item) => <option value={item} key={item}>{businessLabel(item)}</option>)}</select></label>
      <label>결정 사유<select name="reason" required>{reasons.map((item) => <option value={item} key={item}>{businessLabel(item === "OTHER" ? "OTHER_REASON" : item)}</option>)}</select></label>
      <fieldset><legend>결정 근거 <span>정책 규칙 또는 인용 하나 이상</span></legend>{basisOptions.length ? basisOptions.map((option, index) => <label className="check-row" key={`${option.type}-${option.reference_id}`}><input type="checkbox" name="basis" value={index} /><span>{option.label}</span></label>) : <p className="field-help">선택 가능한 정책 근거가 없습니다. 패킷을 다시 확인하세요.</p>}</fieldset>
      <label>판단 근거 설명<textarea name="rationale" minLength={10} maxLength={2000} rows={5} required placeholder="정책 조항과 증거를 바탕으로 판단 이유를 10자 이상 기록하세요." /></label>
      <button className="button button-primary full-button" type="submit" disabled={Boolean(decisionBlockReason) || pending || !basisOptions.some((option) => option.type === "POLICY_RULE_RESULT" || option.type === "POLICY_CITATION")}><CheckCircle2 size={18} />결정 확정</button>
    </form> : <form onSubmit={onEvidence}>
      <label>요청 사유<select name="reason" required><option value="IMAGE_REQUIRED">이미지 필요</option><option value="DEFECT_AREA_NOT_VISIBLE">결함 부위 미식별</option><option value="IMAGE_TOO_DARK">이미지 어두움</option><option value="IMAGE_BLURRED">이미지 흐림</option><option value="DESCRIPTION_INSUFFICIENT">설명 부족</option></select></label>
      <label>고객 안내 문구<textarea name="instructions" rows={4} required maxLength={2000} placeholder="어떤 자료가 왜 필요한지 구체적으로 적으세요." /></label>
      <label>내부 메모<textarea name="rationale" rows={3} maxLength={2000} /></label>
      <button className="button button-secondary full-button" type="submit" disabled={pending}><FileImage size={18} />추가 자료 요청</button>
    </form>}
  </div>;
}
