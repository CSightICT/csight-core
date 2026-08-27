import { ArrowLeft, CheckCircle2, FileImage, FileText, Gavel, LockKeyhole, MessageSquareWarning, ShieldAlert, UserCheck } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { Card, DefinitionList, Loading, Notice, PageHeader, formatDate, friendlyError, shortId, textValue } from "../components/Ui";
import { StatusBadge } from "../components/StatusBadge";

const decisions = ["APPROVE_REFUND", "APPROVE_EXCHANGE", "APPROVE_RESHIPMENT", "APPROVE_REPAIR", "REJECT_REQUEST", "PROVIDE_INFORMATION", "NO_ACTION"];
const reasons = ["POLICY_CONDITION_MET", "POLICY_CONDITION_NOT_MET", "POLICY_EXCEPTION", "EVIDENCE_SUFFICIENT", "EVIDENCE_INSUFFICIENT", "CUSTOMER_INFORMATION_ONLY", "OTHER"];

interface BasisOption { type: string; reference_id: string; label: string }

export function ReviewDetailPage() {
  const { taskId = "" } = useParams();
  const { user, hasRole } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"summary" | "rules" | "citations" | "history">("summary");
  const [actionError, setActionError] = useState<string | null>(null);
  const detail = useQuery({ queryKey: ["review", taskId], queryFn: () => api.getReviewTask(taskId), enabled: Boolean(taskId) });

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

  const basisOptions = useMemo<BasisOption[]>(() => {
    if (!detail.data) return [];
    const options: BasisOption[] = [];
    detail.data.rule_results.forEach((rule) => {
      const id = String(rule.id ?? rule.rule_result_id ?? rule.rule_id ?? "");
      if (id) options.push({ type: "POLICY_RULE_RESULT", reference_id: id, label: `규칙 ${textValue(rule.rule_id ?? id)} · ${textValue(rule.status)}` });
    });
    detail.data.citation_items.forEach((citation, index) => {
      const id = String(citation.citation_id ?? citation.id ?? "");
      if (id) options.push({ type: "POLICY_CITATION", reference_id: id, label: `인용 ${index + 1} · ${textValue(citation.clause_id ?? id)}` });
    });
    const extraction = detail.data.packet.llm_extraction_result_v2_id;
    if (typeof extraction === "string" && extraction) options.push({ type: "ANALYSIS_RESULT", reference_id: extraction, label: `Text v2 분석 · ${shortId(extraction)}` });
    return options;
  }, [detail.data]);

  if (detail.isLoading) return <div className="page"><Loading label="검토 패킷의 무결성을 확인하는 중" /></div>;
  if (detail.error || !detail.data) return <div className="page"><div className="error-panel" role="alert">{friendlyError(detail.error)}</div></div>;
  const { task, packet } = detail.data;
  const safetyBlocked = task.task_type === "SAFETY_REVIEW" && !hasRole("ADMIN");
  const canClaim = !safetyBlocked && (task.status === "PENDING" || (task.status === "ESCALATED" && hasRole("ADMIN")));
  const canAct = task.status === "CLAIMED" && task.current_assignee_id === user?.user_id;

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
    <PageHeader eyebrow={`Review · ${shortId(task.id)}`} title="최종 결정 검토" description={`Case ${shortId(task.case_id)} · 패킷 버전 ${task.version}`}
      actions={<><Link className="button button-ghost" to="/reviews"><ArrowLeft size={18} />검토함</Link><StatusBadge status={task.status} /></>} />
    {actionError && <div className="inline-alert inline-alert-danger" role="alert">{actionError}</div>}
    {safetyBlocked && <Notice tone="danger" title="Safety Case 권한 차단"><span>안전 검토의 최종 결정은 ADMIN만 기록할 수 있습니다. 검토자는 근거를 확인하고 관리자에게 이관할 수 있습니다.</span></Notice>}
    <div className="review-layout">
      <div className="review-body">
        <div className="tabs" role="tablist" aria-label="검토 자료">
          {(["summary", "rules", "citations", "history"] as const).map((item) => <button key={item} type="button" role="tab" aria-selected={tab === item} className={tab === item ? "tab-active" : ""} onClick={() => setTab(item)}>{{ summary: "요약", rules: "정책 규칙", citations: "인용 근거", history: "기록" }[item]}</button>)}
        </div>
        {tab === "summary" && <Card title="검토 패킷" actions={<span className="integrity-badge"><LockKeyhole size={14} />immutable snapshot</span>}>
          <DefinitionList items={[
            { label: "작업 유형", value: task.task_type }, { label: "우선순위", value: task.priority },
            { label: "정책 평가", value: shortId(task.policy_evaluation_run_id) },
            { label: "매핑 규칙", value: `${task.mapping_rule_name} · ${task.mapping_rule_version}` },
            { label: "생성", value: formatDate(task.created_at) },
          ]} />
          <PacketSummary packet={packet} />
          {detail.data.grounded_explanation && <div className="explanation-box"><MessageSquareWarning size={19} /><div><strong>Grounded explanation</strong><p>{textValue(detail.data.grounded_explanation.explanation ?? detail.data.grounded_explanation.summary ?? detail.data.grounded_explanation)}</p></div></div>}
        </Card>}
        {tab === "rules" && <Card title="정책 규칙 결과" description="최종 결정은 이 스냅샷의 규칙 결과를 근거로 선택합니다."><RecordList items={detail.data.rule_results} icon={<Gavel size={17} />} empty="규칙 결과가 없습니다." /></Card>}
        {tab === "citations" && <Card title="Top-3 인용 근거" description="정책 문서 버전과 조항을 함께 확인하세요."><RecordList items={detail.data.citation_items} icon={<FileText size={17} />} empty="인용 근거가 없습니다." /></Card>}
        {tab === "history" && <Card title="Append-only 작업 기록"><RecordList items={detail.data.actions} icon={<UserCheck size={17} />} empty="작업 기록이 없습니다." /></Card>}
      </div>
      <aside className="decision-panel">
        <Card title="검토 작업">
          {task.status === "RESOLVED" ? <><Notice tone="success" title="결정이 고정되었습니다"><span>기존 결정은 변경하지 않습니다. 다른 결정이 발견되면 자동 대체하지 않고 수동 후속 조치로 전환됩니다.</span></Notice><DefinitionList items={Object.entries(detail.data.decision ?? {}).slice(0, 6).map(([label, value]) => ({ label, value: textValue(value) }))} /><Link className="button button-primary full-button" to={`/cases/${task.case_id}`}>Resolution 확인</Link></> : <>
            {canClaim && <button className="button button-primary full-button" disabled={action.isPending} type="button" onClick={() => simpleAction("claim", {})}><UserCheck size={18} />내가 검토하기</button>}
            {task.status === "WAITING_FOR_EVIDENCE" && <button className="button button-primary full-button" disabled={action.isPending} type="button" onClick={() => simpleAction("resume", { rationale: "추가 자료가 제출되어 검토를 재개합니다." })}>검토 재개</button>}
            {canAct && !safetyBlocked && <DecisionForms basisOptions={basisOptions} onEvidence={requestEvidence} onResolve={resolve} pending={action.isPending} />}
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
  const recommendation = packet.recommendation ?? packet.policy_recommendation ?? packet.summary_status;
  const qualification = packet.input_qualification ?? packet.model_qualification;
  return <div className="packet-highlight"><div><span>정책 권고</span><strong>{textValue(recommendation)}</strong></div><div><span>입력 qualification</span><strong>{textValue(qualification)}</strong></div></div>;
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
      <label>최종 결정<select name="decision" required>{decisions.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
      <label>결정 사유<select name="reason" required>{reasons.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
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
