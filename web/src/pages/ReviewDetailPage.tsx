import { ArrowLeft, CheckCircle2, FileCheck2, FileImage, FileText, Gavel, LockKeyhole, MessageSquareWarning, ShieldAlert, ThumbsDown, ThumbsUp, UserCheck } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { Card, DefinitionList, Loading, Notice, PageHeader, formatDate, friendlyError, shortId, textValue } from "../components/Ui";
import { StatusBadge } from "../components/StatusBadge";
import { readSyntheticCommerceContext } from "../commerce/syntheticCommerceContext";
import { demoProductDisplayName } from "../demo/productScenarioCatalog";
import { businessLabel, fieldLabel } from "../presentation/businessLabels";
import { qualificationPresentation } from "../presentation/reviewPresentation";
import { assessQuickReview, quickResolveInput, reviewBasisOptions, type BasisOption, type QuickReviewVerdict } from "../review/quickReview";

const decisions = ["APPROVE_REFUND", "APPROVE_EXCHANGE", "APPROVE_RESHIPMENT", "APPROVE_REPAIR", "REJECT_REQUEST", "PROVIDE_INFORMATION", "NO_ACTION"];
const reasons = ["POLICY_CONDITION_MET", "POLICY_CONDITION_NOT_MET", "POLICY_EXCEPTION", "EVIDENCE_SUFFICIENT", "EVIDENCE_INSUFFICIENT", "CUSTOMER_INFORMATION_ONLY", "OTHER"];

export function ReviewDetailPage() {
  const { taskId = "" } = useParams();
  const { user, hasRole } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"summary" | "rules" | "citations" | "history">("summary");
  const [actionError, setActionError] = useState<string | null>(null);
  const [awaitingReportCaseId, setAwaitingReportCaseId] = useState<string | null>(null);
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
    refetchInterval: (query) => query.state.data ? false : 600,
  });

  useEffect(() => {
    if (awaitingReportCaseId && report.data) navigate(`/cases/${awaitingReportCaseId}/report`, { replace: true });
  }, [awaitingReportCaseId, navigate, report.data]);

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
      if (caseId) setAwaitingReportCaseId(caseId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["review", taskId] }),
        queryClient.invalidateQueries({ queryKey: ["reviews"] }),
        caseId ? queryClient.invalidateQueries({ queryKey: ["resolution", caseId] }) : Promise.resolve(),
        caseId ? queryClient.invalidateQueries({ queryKey: ["report", caseId] }) : Promise.resolve(),
      ]);
    },
    onError: async (cause) => {
      if (cause instanceof ApiError && cause.status === 409) {
        await queryClient.invalidateQueries({ queryKey: ["review", taskId] });
        setActionError("다른 담당자가 먼저 작업을 변경했습니다. 최신 내용을 불러왔으니 다시 확인해 주세요.");
      } else setActionError(friendlyError(cause));
    },
  });

  if (detail.isLoading) return <div className="page"><Loading label="검토 패킷의 무결성을 확인하는 중" /></div>;
  if (detail.error || !detail.data) return <div className="page"><div className="error-panel" role="alert">{friendlyError(detail.error)}</div></div>;
  const { task, packet } = detail.data;
  const commerce = readSyntheticCommerceContext(reviewCase.data?.attributes);
  const productName = commerce?.order.productDisplayName
    ?? (reviewCase.data ? demoProductDisplayName(reviewCase.data.product_ref) : undefined)
    ?? "상품명 확인 중";
  const adminOnlyTask = ["SAFETY_REVIEW", "MANAGER_REVIEW", "POLICY_EXCEPTION_REVIEW"].includes(task.task_type);
  const adminOnlyBlocked = adminOnlyTask && !hasRole("ADMIN");
  const canClaim = !adminOnlyBlocked && (task.status === "PENDING" || (task.status === "ESCALATED" && hasRole("ADMIN")));
  const canAct = task.status === "CLAIMED" && task.current_assignee_id === user?.user_id;
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

  return <div className="page review-detail-page">
    <PageHeader eyebrow={`최종 결정 검토 · ${shortId(task.id)}`} title={productName} description={`문의 번호 ${shortId(task.case_id)} · ${businessLabel(task.task_type)} · 검토 자료 버전 ${task.version}`}
      actions={<><Link className="button button-ghost" to="/reviews"><ArrowLeft size={18} />검토함</Link><StatusBadge status={task.status} /></>} />
    {actionError && <div className="inline-alert inline-alert-danger" role="alert">{actionError}</div>}
    {adminOnlyBlocked && <Notice tone="danger" title="관리자 전용 검토"><span>안전·관리자·정책 예외 검토의 최종 결정은 관리자만 기록할 수 있습니다. 담당자는 근거를 확인한 뒤 관리자에게 이관할 수 있습니다.</span></Notice>}
    <div className="review-layout">
      <div className="review-body">
        <div className="tabs" role="tablist" aria-label="검토 자료">
          {(["summary", "rules", "citations", "history"] as const).map((item) => <button key={item} type="button" role="tab" aria-selected={tab === item} className={tab === item ? "tab-active" : ""} onClick={() => setTab(item)}>{{ summary: "요약", rules: "정책 규칙", citations: "인용 근거", history: "기록" }[item]}</button>)}
        </div>
        {tab === "summary" && <Card title="검토 자료" actions={<span className="integrity-badge"><LockKeyhole size={14} />변경 방지 기록</span>}>
          <DefinitionList items={[
            { label: "작업 유형", value: businessLabel(task.task_type) }, { label: "우선순위", value: businessLabel(task.priority) },
            { label: "생성", value: formatDate(task.created_at) },
          ]} />
          <PacketSummary packet={packet} />
          {detail.data.grounded_explanation && <div className="explanation-box"><MessageSquareWarning size={19} /><div><strong>정책 근거 확인 요약</strong><span>담당자 판단 참고</span><p>{textValue(detail.data.grounded_explanation.explanation ?? detail.data.grounded_explanation.summary ?? detail.data.grounded_explanation)}</p></div></div>}
          <details className="review-technical-details"><summary>기술 정보 보기</summary><DefinitionList items={[
            { label: "정책 평가 번호", value: shortId(task.policy_evaluation_run_id) },
            { label: "검토 기준 버전", value: `${task.mapping_rule_name} · ${task.mapping_rule_version}` },
          ]} /></details>
        </Card>}
        {tab === "rules" && <Card title="정책 규칙 결과" description="최종 결정은 이 스냅샷의 규칙 결과를 근거로 선택합니다."><RecordList items={detail.data.rule_results} icon={<Gavel size={17} />} empty="규칙 결과가 없습니다." /></Card>}
        {tab === "citations" && <Card title="Top-3 인용 근거" description="정책 문서 버전과 조항을 함께 확인하세요."><RecordList items={detail.data.citation_items} icon={<FileText size={17} />} empty="인용 근거가 없습니다." /></Card>}
        {tab === "history" && <Card title="Append-only 작업 기록"><RecordList items={detail.data.actions} icon={<UserCheck size={17} />} empty="작업 기록이 없습니다." /></Card>}
      </div>
      <aside className="decision-panel">
        <Card title="검토 작업">
          {task.status === "RESOLVED" ? <><Notice tone="success" title="결정이 고정되었습니다"><span>기존 결정은 변경하지 않습니다. 다른 결정이 발견되면 자동 대체하지 않고 수동 후속 조치로 전환됩니다.</span></Notice><DefinitionList items={Object.entries(detail.data.decision ?? {}).slice(0, 6).map(([label, value]) => ({ label: fieldLabel(label), value: Array.isArray(value) ? value.map(businessLabel).join(", ") : businessLabel(value) }))} /><Link className="button button-primary full-button" to={`/cases/${task.case_id}/report`}><FileCheck2 size={18} />최종 검토 문서 보기</Link><Link className="button button-ghost full-button" to={`/cases/${task.case_id}`}>처리 결과 확인</Link></> : <>
            {canQuickReview && quickReview && <QuickReviewPanel assessment={quickReview} pending={quickAction.isPending || Boolean(awaitingReportCaseId)} onVerdict={(verdict) => quickAction.mutate(verdict)} />}
            {awaitingReportCaseId && <Notice tone="success" title="결정 기록 완료 · 문서 생성 중"><span>최종 결정과 처리 사전 확인 결과를 반영한 검토 문서가 준비되면 자동으로 열립니다.</span></Notice>}
            {canClaim && !canQuickReview && <button className="button button-primary full-button" disabled={action.isPending} type="button" onClick={() => simpleAction("claim", {})}><UserCheck size={18} />내가 검토하기</button>}
            {task.status === "WAITING_FOR_EVIDENCE" && <button className="button button-primary full-button" disabled={action.isPending} type="button" onClick={() => simpleAction("resume", { rationale: "추가 자료가 제출되어 검토를 재개합니다." })}>검토 재개</button>}
            {canAct && !adminOnlyBlocked && <details className="manual-review-details"><summary>상세 결정 또는 자료 요청</summary><DecisionForms basisOptions={basisOptions} onEvidence={requestEvidence} onResolve={resolve} pending={action.isPending} /></details>}
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
  </div>;
}

function PacketSummary({ packet }: { packet: Record<string, unknown> }) {
  const recommendation = packet.policy_summary_status ?? packet.recommendation ?? packet.policy_recommendation ?? packet.summary_status;
  const qualification = packet.qualification_snapshot ?? packet.input_qualification ?? packet.model_qualification;
  const qualificationItems = qualificationPresentation(qualification);
  return <div className="packet-highlight"><div className="policy-recommendation"><span>정책 권고</span><strong>{businessLabel(recommendation)}</strong><small>정책은 참고 기준이며 최종 결정은 담당자가 기록합니다.</small></div><div><span>분석 확인 상태</span><ul className="qualification-list">{qualificationItems.map((item) => <li key={item.label}><span>{item.label}</span><strong className={`qualification-${item.tone}`}>{item.status}</strong></li>)}</ul></div></div>;
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
    <p>정책 근거는 자동 첨부되고, 결정 기록부터 처리 사전 확인 및 최종 검토 문서 생성까지 이어집니다.</p>
    <div className="quick-review-meter"><span style={{ width: `${percent}%` }} /><i style={{ left: `${threshold}%` }} /></div>
    <small>빠른 검토 기준 {threshold}% · 모델 정확도가 아닌 정책·근거·입력 준비도입니다.</small>
    <div className="quick-verdict-actions">
      <button className="button quick-allow" type="button" disabled={pending || !assessment.allowDecision} onClick={() => onVerdict("ALLOW")}><ThumbsUp size={20} /><span><strong>{assessment.allowLabel}</strong><small>즉시 확정하고 문서 생성</small></span></button>
      <button className="button quick-deny" type="button" disabled={pending} onClick={() => onVerdict("DENY")}><ThumbsDown size={20} /><span><strong>비허용</strong><small>거절 결정과 문서 생성</small></span></button>
    </div>
    {!assessment.allowDecision && <p className="quick-review-note">정책 효과에서 처리 유형이 하나로 정해지지 않아 허용은 상세 검토가 필요합니다. 비허용은 바로 기록할 수 있습니다.</p>}
    <p className="quick-review-warning"><LockKeyhole size={14} />버튼을 누르면 로그인한 담당자의 변경 불가능한 최종 결정으로 기록됩니다.</p>
  </section>;
}

function RecordList({ items, icon, empty }: { items: Array<Record<string, unknown>>; icon: React.ReactNode; empty: string }) {
  if (!items.length) return <p className="muted-copy">{empty}</p>;
  return <div className="record-list">{items.map((item, index) => <article key={String(item.id ?? item.citation_id ?? index)}><span className="record-icon">{icon}</span><div>{Object.entries(item).slice(0, 8).map(([key, value]) => <div className="record-pair" key={key}><strong>{key}</strong><span>{textValue(value)}</span></div>)}</div></article>)}</div>;
}

function DecisionForms({ basisOptions, onEvidence, onResolve, pending }: {
  basisOptions: BasisOption[];
  onEvidence(event: FormEvent<HTMLFormElement>): void;
  onResolve(event: FormEvent<HTMLFormElement>): void;
  pending: boolean;
}) {
  const [mode, setMode] = useState<"resolve" | "evidence">("resolve");
  return <div className="decision-forms">
    <div className="segmented"><button type="button" className={mode === "resolve" ? "active" : ""} onClick={() => setMode("resolve")}>결정</button><button type="button" className={mode === "evidence" ? "active" : ""} onClick={() => setMode("evidence")}>자료 요청</button></div>
    {mode === "resolve" ? <form onSubmit={onResolve} data-testid="resolve-form">
      <label>최종 결정<select name="decision" required>{decisions.map((item) => <option value={item} key={item}>{businessLabel(item)}</option>)}</select></label>
      <label>결정 사유<select name="reason" required>{reasons.map((item) => <option value={item} key={item}>{businessLabel(item === "OTHER" ? "OTHER_REASON" : item)}</option>)}</select></label>
      <fieldset><legend>결정 근거 <span>정책 규칙 또는 인용 하나 이상</span></legend>{basisOptions.length ? basisOptions.map((option, index) => <label className="check-row" key={`${option.type}-${option.reference_id}`}><input type="checkbox" name="basis" value={index} /><span>{option.label}</span></label>) : <p className="field-help">선택 가능한 정책 근거가 없습니다. 패킷을 다시 확인하세요.</p>}</fieldset>
      <label>판단 근거 설명<textarea name="rationale" minLength={10} maxLength={2000} rows={5} required placeholder="정책 조항과 증거를 바탕으로 판단 이유를 10자 이상 기록하세요." /></label>
      <button className="button button-primary full-button" type="submit" disabled={pending || !basisOptions.some((option) => option.type === "POLICY_RULE_RESULT" || option.type === "POLICY_CITATION")}><CheckCircle2 size={18} />결정 확정</button>
    </form> : <form onSubmit={onEvidence}>
      <label>요청 사유<select name="reason" required><option value="IMAGE_REQUIRED">이미지 필요</option><option value="DEFECT_AREA_NOT_VISIBLE">결함 부위 미식별</option><option value="IMAGE_TOO_DARK">이미지 어두움</option><option value="IMAGE_BLURRED">이미지 흐림</option><option value="DESCRIPTION_INSUFFICIENT">설명 부족</option></select></label>
      <label>고객 안내 문구<textarea name="instructions" rows={4} required maxLength={2000} placeholder="어떤 자료가 왜 필요한지 구체적으로 적으세요." /></label>
      <label>내부 메모<textarea name="rationale" rows={3} maxLength={2000} /></label>
      <button className="button button-secondary full-button" type="submit" disabled={pending}><FileImage size={18} />추가 자료 요청</button>
    </form>}
  </div>;
}
