import {
  Activity, ArrowLeft, Camera, CheckCircle2, ClipboardCheck, ExternalLink, FileImage, FileText,
  ImagePlus, Play, RefreshCw, ShieldAlert, ShieldCheck, Sparkles,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type ChangeEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, api } from "../api/client";
import type { WorkflowProgress } from "../workflow/runPolicyWorkflow";
import { runPolicyWorkflow } from "../workflow/runPolicyWorkflow";
import { Card, DefinitionList, EmptyState, Loading, Notice, PageHeader, StepRow, formatDate, friendlyError, shortId, textValue } from "../components/Ui";
import { StatusBadge } from "../components/StatusBadge";
import { checkpointStore, newOpaqueKey } from "../recovery/workflowCheckpoint";
import { formatVisionProbability, readBinaryVisionAssessments } from "../vision/imageAssessment";

const terminal = new Set(["SUCCEEDED", "PARTIAL_SUCCESS", "FAILED"]);

function isUnavailable(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

export function CaseWorkspacePage() {
  const { caseId = "" } = useParams();
  const queryClient = useQueryClient();
  const [checkpoint, setCheckpoint] = useState(() => checkpointStore.load(caseId));
  const [progress, setProgress] = useState<WorkflowProgress[]>([]);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [visionError, setVisionError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const caseQuery = useQuery({ queryKey: ["case", caseId], queryFn: () => api.getCase(caseId), enabled: Boolean(caseId) });
  const analysisQuery = useQuery({
    queryKey: ["analysis", caseId, checkpoint.analysisV2RunId],
    queryFn: () => api.getAnalysis(caseId, checkpoint.analysisV2RunId!),
    enabled: Boolean(checkpoint.analysisV2RunId),
  });
  const retrievalQuery = useQuery({
    queryKey: ["retrieval", caseId, checkpoint.retrievalRunId],
    queryFn: () => api.getRetrieval(caseId, checkpoint.retrievalRunId!),
    enabled: Boolean(checkpoint.retrievalRunId),
  });
  const groundingQuery = useQuery({
    queryKey: ["grounding", caseId, checkpoint.groundingRunId],
    queryFn: () => api.getGrounding(caseId, checkpoint.groundingRunId!),
    enabled: Boolean(checkpoint.groundingRunId),
  });
  const policyQuery = useQuery({
    queryKey: ["policy", caseId, checkpoint.policyEvaluationRunId],
    queryFn: () => api.getPolicy(caseId, checkpoint.policyEvaluationRunId!),
    enabled: Boolean(checkpoint.policyEvaluationRunId),
  });
  const visionQuery = useQuery({
    queryKey: ["vision", caseId, checkpoint.visionRunId],
    queryFn: () => api.getAnalysis(caseId, checkpoint.visionRunId!),
    enabled: Boolean(checkpoint.visionRunId),
    refetchInterval: (query) => {
      const status = query.state.data?.run.status;
      return status && !terminal.has(status) ? 1600 : false;
    },
  });
  const reviewsQuery = useQuery({ queryKey: ["case-reviews", caseId], queryFn: () => api.listCaseReviewTasks(caseId), enabled: Boolean(caseId), refetchInterval: running ? 2000 : false });
  const resolutionQuery = useQuery({ queryKey: ["resolution", caseId], queryFn: () => api.getResolution(caseId), enabled: Boolean(caseId), retry: false });
  const eventsQuery = useQuery({ queryKey: ["resolution-events", caseId], queryFn: () => api.listResolutionEvents(caseId), enabled: Boolean(caseId), retry: false });
  const intentsQuery = useQuery({ queryKey: ["intents", caseId], queryFn: () => api.listIntents(caseId), enabled: Boolean(caseId), retry: false });
  const firstIntentId = intentsQuery.data?.[0]?.id;
  const intentDetailQuery = useQuery({
    queryKey: ["intent-detail", firstIntentId],
    queryFn: () => api.getIntent(firstIntentId!),
    enabled: Boolean(firstIntentId),
    retry: false,
  });

  const evidenceMutation = useMutation({
    mutationFn: (file: File) => api.uploadEvidence(caseId, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["case", caseId] }),
  });

  async function startPolicyFlow() {
    if (!caseQuery.data) return;
    setRunning(true);
    setWorkflowError(null);
    setProgress([]);
    abortRef.current = new AbortController();
    try {
      await runPolicyWorkflow(api, caseId, caseQuery.data.created_at.slice(0, 10), {
        signal: abortRef.current.signal,
        onProgress: (item) => setProgress((items) => {
          const next = items.filter((existing) => existing.stage !== item.stage);
          return [...next, item];
        }),
      });
      setCheckpoint(checkpointStore.load(caseId));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["analysis", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["retrieval", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["grounding", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["policy", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["case-reviews", caseId] }),
      ]);
    } catch (cause) {
      setCheckpoint(checkpointStore.load(caseId));
      if (!(cause instanceof DOMException && cause.name === "AbortError")) setWorkflowError(friendlyError(cause));
    } finally {
      setRunning(false);
    }
  }

  async function startVision() {
    setVisionError(null);
    let current = checkpointStore.load(caseId);
    const key = current.idempotencyKeys.vision ?? newOpaqueKey();
    if (!current.idempotencyKeys.vision) current = checkpointStore.patch(caseId, { idempotencyKeys: { ...current.idempotencyKeys, vision: key } });
    try {
      if (!current.visionRunId) {
        const started = await api.startAnalysis(caseId, "product_defect_multimodal_analysis", "1.0.0", key);
        current = checkpointStore.patch(caseId, { visionRunId: started.analysis_run_id });
      }
      setCheckpoint(current);
    } catch (cause) {
      setVisionError(friendlyError(cause));
    }
  }

  function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) evidenceMutation.mutate(file);
    event.target.value = "";
  }

  if (caseQuery.isLoading) return <div className="page"><Loading label="케이스 작업 공간을 준비하는 중" /></div>;
  if (caseQuery.error || !caseQuery.data) return <div className="page"><div className="error-panel" role="alert">{friendlyError(caseQuery.error)}</div></div>;
  const item = caseQuery.data;
  const review = reviewsQuery.data?.[0];

  return <div className="page workspace-page">
    <PageHeader eyebrow={`Case · ${shortId(caseId)}`} title={item.order_ref} description={`${item.product_ref} · ${formatDate(item.created_at)} 접수`}
      actions={<><Link className="button button-ghost" to="/cases"><ArrowLeft size={18} />목록</Link><StatusBadge status={item.status} /></>} />

    <div className="workspace-grid">
      <div className="workspace-main">
        <Card title="상담 내용" actions={<span className="request-pill">{item.requested_action}</span>}>
          <p className="customer-message">{item.customer_message}</p>
          <DefinitionList items={[
            { label: "주문 참조", value: item.order_ref },
            { label: "상품 참조", value: item.product_ref },
            { label: "제공된 조치 입력", value: Object.keys(item.attributes).length ? "있음" : "없음" },
          ]} />
        </Card>

        <Card title="정책 검토 흐름" description="콘솔이 기존 실행 API를 안전한 순서로 연결합니다." className="spaced-card"
          actions={<button className="button button-primary" type="button" disabled={running} onClick={startPolicyFlow}><Play size={17} />{running ? "진행 중…" : checkpoint.analysisV2RunId ? "이어 확인" : "분석 시작"}</button>}>
          <Notice title="고정된 기본 경로"><span>Text v2 → RAW 질의 → HYBRID 검색 → Top-3 인용 → 근거 연결 → 정책 평가 순서입니다. Reranker와 LLM Query Builder는 사용하지 않습니다.</span></Notice>
          {workflowError && <div className="inline-alert inline-alert-danger" role="alert">{workflowError}</div>}
          <div className="workflow-steps" data-testid="policy-workflow">
            <StepRow label="1. 상담 내용 구조화 (Text v2)" detail="고객 원문에서 요청·결함·누락 정보를 분리합니다." status={analysisQuery.data?.run.status ?? progress.find((p) => p.stage === "TEXT_V2")?.status ?? "PENDING"} />
            <StepRow label="2. RAW + HYBRID 정책 검색" detail="원문 기반으로 정책 조항 3개까지 찾습니다." status={retrievalQuery.data?.run.status ?? progress.find((p) => p.stage === "RAW_TOP3")?.status ?? "PENDING"} />
            <StepRow label="3. 인용과 설명 연결" detail="정책 문구가 설명을 실제로 뒷받침하는지 확인합니다." status={groundingQuery.data?.run.status ?? progress.find((p) => p.stage === "GROUNDING")?.status ?? "PENDING"} />
            <StepRow label="4. 정책 규칙 평가" detail="버전과 효력일이 고정된 규칙으로 권고를 만듭니다." status={policyQuery.data?.run.status ?? progress.find((p) => p.stage === "POLICY")?.status ?? "PENDING"} />
            <StepRow label="5. 사람 검토" detail="최종 결정은 담당자 또는 권한 있는 관리자가 내립니다." status={review?.status ?? progress.find((p) => p.stage === "REVIEW")?.status ?? "PENDING"} />
          </div>
          <PolicyEvidence retrieval={retrievalQuery.data} grounding={groundingQuery.data} policy={policyQuery.data} />
        </Card>

        <ResolutionPanel caseId={caseId} resolutionQuery={resolutionQuery} eventsQuery={eventsQuery} intentsQuery={intentsQuery} intentDetailQuery={intentDetailQuery} />
      </div>

      <aside className="workspace-aside">
        <Card title="증거 자료" description={`${item.evidence.length}개 첨부`} actions={<label className="button button-secondary button-small file-button"><ImagePlus size={16} />추가<input type="file" accept="image/jpeg,image/png,image/webp" onChange={upload} disabled={evidenceMutation.isPending} /></label>}>
          {evidenceMutation.error && <div className="inline-alert inline-alert-danger" role="alert">{friendlyError(evidenceMutation.error)}</div>}
          {evidenceMutation.isPending && <Loading label="이미지를 안전하게 업로드하는 중" />}
          {item.evidence.length === 0 ? <EmptyState title="이미지가 없습니다"><span>이미지 기반 분석을 하려면 결함이 보이는 사진을 추가하세요.</span></EmptyState> : <div className="evidence-list">{item.evidence.map((evidence) => <button className="evidence-row" type="button" key={evidence.evidence_id} onClick={() => api.openEvidence(caseId, evidence.evidence_id)}>
            <span><FileImage size={19} /></span><div><strong>{evidence.original_filename}</strong><small>{Math.ceil(evidence.size_bytes / 1024)} KB · {evidence.width}×{evidence.height}</small></div><ExternalLink size={15} />
          </button>)}</div>}
        </Card>

        <Card title="Vision 분석" description="정책 경로와 분리된 참고 실행" className="spaced-card" actions={<Camera size={20} className="muted-icon" />}>
          <Notice tone="warning" title="Mock qualification"><span>현재 Vision은 Mock 등급입니다. 결과는 정책 평가의 입력이나 자동 결정으로 사용하지 않습니다.</span></Notice>
          {visionError && <div className="inline-alert inline-alert-danger" role="alert">{visionError}</div>}
          {visionQuery.data ? <VisionResult detail={visionQuery.data} /> : <button className="button button-secondary full-button" type="button" disabled={item.evidence.length === 0} onClick={startVision}><Sparkles size={17} />별도 Vision 실행</button>}
        </Card>

        <Card title="사람 검토" className="spaced-card" actions={<ClipboardCheck size={20} className="muted-icon" />}>
          {review ? <div className="review-compact"><StatusBadge status={review.status} /><DefinitionList items={[
            { label: "유형", value: review.task_type }, { label: "우선순위", value: review.priority }, { label: "버전", value: review.version },
          ]} /><Link className="button button-primary full-button" to={`/reviews/${review.id}`}>검토 열기</Link></div> : <EmptyState title="아직 검토 작업이 없습니다"><span>정책 평가가 완료되면 검토 작업이 생성됩니다.</span></EmptyState>}
        </Card>
      </aside>
    </div>
  </div>;
}

function PolicyEvidence({ retrieval, grounding, policy }: {
  retrieval: ReturnType<typeof api.getRetrieval> extends Promise<infer T> ? T | undefined : never;
  grounding: ReturnType<typeof api.getGrounding> extends Promise<infer T> ? T | undefined : never;
  policy: ReturnType<typeof api.getPolicy> extends Promise<infer T> ? T | undefined : never;
}) {
  if (!retrieval && !grounding && !policy) return null;
  const citations = grounding?.citation_pack?.citations;
  const citationCount = Array.isArray(citations) ? citations.length : retrieval?.hits.length ?? 0;
  return <div className="result-stack">
    {retrieval && <div className="result-block"><div className="result-heading"><FileText size={18} /><strong>정책 후보</strong><span>{retrieval.hits.length}개</span></div><div className="chip-row"><span className="data-chip">RAW Query</span><span className="data-chip">{textValue(retrieval.retrieval_profile.base_mode ?? "HYBRID")}</span><span className="data-chip">Reranker Off</span><span className="data-chip">Top-{retrieval.run.top_k}</span></div>
      <ol className="citation-list">{retrieval.hits.slice(0, 3).map((hit, index) => <li key={String(hit.clause_id ?? index)}><strong>{String(hit.clause_id ?? `정책 조항 ${index + 1}`)}</strong><span>{String(hit.document_version ?? hit.document_id ?? "버전 정보 없음")}</span></li>)}</ol></div>}
    {grounding && <div className="result-block"><div className="result-heading"><ShieldCheck size={18} /><strong>근거 연결</strong><StatusBadge status={grounding.run.status} subtle /></div><p>{citationCount}개 인용 근거 · 구조 검증 {grounding.structural_validation ? "기록됨" : "대기"}</p></div>}
    {policy && <div className="result-block"><div className="result-heading"><CheckCircle2 size={18} /><strong>정책 평가</strong><StatusBadge status={policy.run.status} subtle /></div><div className="chip-row">{Object.entries(policy.input_qualification).map(([key, value]) => <span className="data-chip" key={key}>{key}: {value}</span>)}</div><p>{policy.rule_results.length}개 규칙 결과가 검토 패킷에 고정됩니다.</p></div>}
  </div>;
}

function VisionResult({ detail }: { detail: Awaited<ReturnType<typeof api.getAnalysis>> }) {
  const assessments = readBinaryVisionAssessments(detail.vision_results);
  return <div className="vision-result" data-testid="vision-result"><div className="result-heading"><Activity size={18} /><strong>별도 실행</strong><StatusBadge status={detail.run.status} /></div>
    <DefinitionList items={[
      { label: "파이프라인", value: "Multimodal v1" }, { label: "실행 ID", value: shortId(detail.run.analysis_run_id) }, { label: "Vision 결과", value: detail.vision_results.length },
    ]} />
    {assessments.map((assessment, index) => <div className="result-stack" data-testid="binary-vision-assessment" key={assessment.evidenceId ?? `assessment-${index}`}>
      <Notice tone={assessment.isCandidate ? "warning" : "info"} title={assessment.isCandidate ? "결함 고신뢰 후보" : "고신뢰 기준 미달 · 정상 판정 아님"}>
        <span>이미지 전체의 결함 유무 점수만 제공하는 상담원 참고 신호입니다. 결함 종류와 위치는 생성하지 않습니다.</span>
      </Notice>
      <DefinitionList items={[
        { label: "이상 후보 점수", value: formatVisionProbability(assessment.score) },
        { label: "동결 기준", value: `${formatVisionProbability(assessment.threshold)} 이상` },
        { label: "결함 종류·위치", value: "제공하지 않음" },
        { label: "자동 결정", value: "허용 안 함" },
      ]} />
      <p className="muted-copy">{assessment.qualification === "SYNTHETIC_MOCK"
        ? "현재 결과는 이진 계약을 검증하는 합성 Mock 실행이며 실제 E3 checkpoint 추론이 아닙니다."
        : assessment.qualification === "REMOTE_UNQUALIFIED"
          ? `원격 Provider ${assessment.modelName ?? "identity 미상"} 결과입니다. 실제 E3 qualification은 별도 external gate 증거로 확인해야 합니다.`
          : "Provider qualification을 확인할 수 없어 이 결과를 실제 E3 추론으로 해석할 수 없습니다."}</p>
    </div>)}
    {detail.run.status === "PARTIAL_SUCCESS" && <Notice tone="warning" title="부분 완료"><span>Vision 실패 또는 시간 초과가 기록되었습니다. 자동 결정·외부 조치는 생성하지 않으며 사람 검토가 필요합니다.</span></Notice>}
  </div>;
}

interface QueryLike<T> { data: T | undefined; error: Error | null; isLoading: boolean; refetch(): unknown }

function ResolutionPanel({ caseId, resolutionQuery, eventsQuery, intentsQuery, intentDetailQuery }: {
  caseId: string;
  resolutionQuery: QueryLike<Awaited<ReturnType<typeof api.getResolution>>>;
  eventsQuery: QueryLike<Awaited<ReturnType<typeof api.listResolutionEvents>>>;
  intentsQuery: QueryLike<Awaited<ReturnType<typeof api.listIntents>>>;
  intentDetailQuery: QueryLike<Awaited<ReturnType<typeof api.getIntent>>>;
}) {
  const unavailable = isUnavailable(resolutionQuery.error);
  const status = resolutionQuery.data?.status;
  const intent = intentsQuery.data?.[0];
  const attempts = intentDetailQuery.data?.attempts.length ?? 0;
  const results = intentDetailQuery.data?.results.length ?? 0;
  const sideEffects = intentDetailQuery.data?.results.some((result) => result.side_effects_performed === true) ?? false;
  return <Card title="Resolution · DRY-RUN" description="사람의 결정과 외부 조치 시뮬레이션은 Case 상태와 별도로 기록됩니다." className="spaced-card"
    actions={<button className="icon-button" type="button" aria-label="Resolution 새로고침" onClick={() => { resolutionQuery.refetch(); eventsQuery.refetch(); intentsQuery.refetch(); intentDetailQuery.refetch(); }}><RefreshCw size={18} /></button>}>
    {resolutionQuery.isLoading ? <Loading label="Resolution을 확인하는 중" /> : unavailable ? <EmptyState title="아직 Resolution이 없습니다"><span>검토자가 최종 결정을 기록하면 안전한 Resolution 흐름이 시작됩니다.</span></EmptyState> : resolutionQuery.error ? <div className="inline-alert inline-alert-danger" role="alert">{friendlyError(resolutionQuery.error)}</div> : <>
      <div className="resolution-hero" data-testid="resolution-status"><span className="resolution-icon">{status === "ACTION_NEEDS_INPUT" ? <ShieldAlert /> : <ShieldCheck />}</span><div><p className="eyebrow">현재 단계</p><h3>{status ?? "DECISION_RECORDED"}</h3></div>{status && <StatusBadge status={status} />}</div>
      {status === "ACTION_NEEDS_INPUT" && <Notice tone="warning" title="외부 조치 입력이 부족합니다"><span>입력 보완 기능은 5C 범위에 포함되지 않습니다. Command·Attempt·Result를 만들지 않고 안전하게 보류합니다.</span></Notice>}
      <DefinitionList items={[
        { label: "결정 ID", value: textValue(resolutionQuery.data?.source_human_decision_id) },
        { label: "Action Intent", value: intent ? textValue(intent.action_type) : "0개" },
        { label: "Simulation Attempt", value: attempts },
        { label: "Simulation Result", value: results },
        { label: "실제 부작용", value: sideEffects ? "발생" : "없음" },
      ]} />
      {intent && <Notice tone="success" title="DRY-RUN 전용"><span>네트워크를 사용하지 않는 결정론적 시뮬레이션입니다. LIVE 요청은 항상 차단되고 side_effects_performed=false여야 합니다.</span></Notice>}
      <div className="card-footer-actions"><span>{eventsQuery.data?.length ?? 0}개 append-only 이벤트</span><Link className="button button-secondary" to={`/cases/${caseId}/report`}><FileText size={17} />최종 보고서</Link></div>
    </>}
  </Card>;
}
