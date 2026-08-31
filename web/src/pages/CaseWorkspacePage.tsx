import {
  Activity, ArrowLeft, Camera, CheckCircle2, ClipboardCheck, FileText,
  ImagePlus, Play, RefreshCw, ShieldAlert, ShieldCheck, Sparkles,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { findLatestCaseAnalysisRuns, findLatestPolicyRunSet } from "../analysis/runRecovery";
import { ApiError, api } from "../api/client";
import { EvidencePreview } from "../evidence/EvidencePreview";
import { demoProductDisplayName, demoProductScenario, formatSyntheticPriceBand } from "../demo/productScenarioCatalog";
import { businessLabel, operationalReference } from "../presentation/businessLabels";
import { demoPocClosedSet } from "../demo/pocClosedSetCatalog";
import { PolicyCitationList } from "../policy/PolicyCitationList";
import { DemoProvenance, readDemoImageObservation, readDemoProvenance } from "../provenance/DemoProvenance";
import type { WorkflowProgress } from "../workflow/runPolicyWorkflow";
import { runPolicyWorkflow } from "../workflow/runPolicyWorkflow";
import { Card, DefinitionList, EmptyState, Loading, Notice, PageHeader, StepRow, formatDate, friendlyError, shortId, textValue } from "../components/Ui";
import { StatusBadge } from "../components/StatusBadge";
import { formatCommerceMoney, readSyntheticCommerceContext } from "../commerce/syntheticCommerceContext";
import { resetFailedTextCheckpoint, resetFailedVisionCheckpoint } from "../recovery/failedRunReset";
import { checkpointStore, newOpaqueKey } from "../recovery/workflowCheckpoint";
import { describeVisionQualification, formatVisionProbability, readBinaryVisionAssessments } from "../vision/imageAssessment";
import { policyAsOfDate } from "../workflow/policyDate";
import { DEFAULT_WORKFLOW_MAX_WAIT_MS, workflowPollDelay, workflowWaitExpired } from "../workflow/snapshotPolling";

const terminal = new Set(["SUCCEEDED", "COMPLETED", "PARTIAL_SUCCESS", "FAILED"]);

function isUnavailable(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

export function CaseWorkspacePage() {
  const { caseId = "" } = useParams();
  return <CaseWorkspace caseId={caseId} key={caseId} />;
}

function CaseWorkspace({ caseId }: { caseId: string }) {
  const queryClient = useQueryClient();
  const [checkpoint, setCheckpoint] = useState(() => checkpointStore.load(caseId));
  const [progress, setProgress] = useState<WorkflowProgress[]>([]);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [snapshotPaused, setSnapshotPaused] = useState(false);
  const [snapshotTimedOut, setSnapshotTimedOut] = useState(false);
  const [textRetrying, setTextRetrying] = useState(false);
  const [visionRetrying, setVisionRetrying] = useState(false);
  const [visionError, setVisionError] = useState<string | null>(null);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const snapshotPollStartedAt = useRef<number | null>(null);
  const snapshotPollAttempt = useRef(0);
  const observedSnapshotTransitions = useRef(new Set<string>());
  const needsRunRecovery = !checkpoint.analysisV2RunId || !checkpoint.visionRunId;

  const caseQuery = useQuery({ queryKey: ["case", caseId], queryFn: () => api.getCase(caseId), enabled: Boolean(caseId) });
  const analysisRunsQuery = useQuery({
    queryKey: ["analysis-runs", caseId],
    queryFn: () => api.listAnalysis(caseId),
    enabled: Boolean(caseId) && needsRunRecovery,
    retry: false,
  });
  const recoveredRuns = analysisRunsQuery.data
    ? findLatestCaseAnalysisRuns(analysisRunsQuery.data)
    : { textV2RunId: null, visionRunId: null };
  const analysisV2RunId = checkpoint.analysisV2RunId ?? recoveredRuns.textV2RunId;
  const visionRunId = checkpoint.visionRunId ?? recoveredRuns.visionRunId;
  const needsPolicyRecovery = !checkpoint.retrievalRunId
    || !checkpoint.groundingRunId
    || !checkpoint.policyEvaluationRunId;
  const policyHistoryEnabled = Boolean(caseId && analysisV2RunId && needsPolicyRecovery);
  const retrievalRunsQuery = useQuery({
    queryKey: ["retrieval-runs", caseId],
    queryFn: () => api.listRetrieval(caseId),
    enabled: policyHistoryEnabled,
    retry: false,
  });
  const groundingRunsQuery = useQuery({
    queryKey: ["grounding-runs", caseId],
    queryFn: () => api.listGrounding(caseId),
    enabled: policyHistoryEnabled,
    retry: false,
  });
  const policyRunsQuery = useQuery({
    queryKey: ["policy-runs", caseId],
    queryFn: () => api.listPolicy(caseId),
    enabled: policyHistoryEnabled,
    retry: false,
  });
  const policyHistoryReady = policyHistoryEnabled
    && retrievalRunsQuery.data !== undefined
    && groundingRunsQuery.data !== undefined
    && policyRunsQuery.data !== undefined;
  const recoveredPolicyRuns = policyHistoryReady
    ? findLatestPolicyRunSet(
      analysisV2RunId!,
      retrievalRunsQuery.data,
      groundingRunsQuery.data,
      policyRunsQuery.data,
      {
        ...(checkpoint.retrievalRunId ? { retrievalRunId: checkpoint.retrievalRunId } : {}),
        ...(checkpoint.groundingRunId ? { groundingRunId: checkpoint.groundingRunId } : {}),
        ...(checkpoint.policyEvaluationRunId
          ? { policyEvaluationRunId: checkpoint.policyEvaluationRunId }
          : {}),
      },
    )
    : { retrievalRunId: null, groundingRunId: null, policyEvaluationRunId: null };
  const retrievalRunId = checkpoint.retrievalRunId ?? recoveredPolicyRuns.retrievalRunId;
  const groundingRunId = checkpoint.groundingRunId ?? recoveredPolicyRuns.groundingRunId;
  const policyEvaluationRunId = checkpoint.policyEvaluationRunId
    ?? recoveredPolicyRuns.policyEvaluationRunId;
  const workflowSnapshotQuery = useQuery({
    queryKey: ["workflow-snapshot", caseId],
    queryFn: () => api.getWorkflowSnapshot(caseId),
    enabled: Boolean(caseId),
    retry: 1,
  });
  const refetchWorkflowSnapshot = workflowSnapshotQuery.refetch;
  const analysisQuery = useQuery({
    queryKey: ["analysis", caseId, analysisV2RunId],
    queryFn: () => api.getAnalysis(caseId, analysisV2RunId!),
    enabled: Boolean(analysisV2RunId),
    refetchInterval: false,
  });
  const retrievalQuery = useQuery({
    queryKey: ["retrieval", caseId, retrievalRunId],
    queryFn: () => api.getRetrieval(caseId, retrievalRunId!),
    enabled: Boolean(retrievalRunId),
    refetchInterval: false,
  });
  const groundingQuery = useQuery({
    queryKey: ["grounding", caseId, groundingRunId],
    queryFn: () => api.getGrounding(caseId, groundingRunId!),
    enabled: Boolean(groundingRunId),
    refetchInterval: false,
  });
  const policyQuery = useQuery({
    queryKey: ["policy", caseId, policyEvaluationRunId],
    queryFn: () => api.getPolicy(caseId, policyEvaluationRunId!),
    enabled: Boolean(policyEvaluationRunId),
    refetchInterval: false,
  });
  const visionQuery = useQuery({
    queryKey: ["vision", caseId, visionRunId],
    queryFn: () => api.getAnalysis(caseId, visionRunId!),
    enabled: Boolean(visionRunId),
    refetchInterval: false,
  });
  const reviewsQuery = useQuery({ queryKey: ["case-reviews", caseId], queryFn: () => api.listCaseReviewTasks(caseId), enabled: Boolean(caseId), refetchInterval: false });
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

  useEffect(() => {
    const stored = checkpointStore.load(caseId);
    if (
      analysisV2RunId === stored.analysisV2RunId
      && visionRunId === stored.visionRunId
      && retrievalRunId === stored.retrievalRunId
      && groundingRunId === stored.groundingRunId
      && policyEvaluationRunId === stored.policyEvaluationRunId
    ) return;
    const next = { ...stored };
    if (analysisV2RunId) next.analysisV2RunId = analysisV2RunId;
    if (visionRunId) next.visionRunId = visionRunId;
    if (retrievalRunId) next.retrievalRunId = retrievalRunId;
    if (groundingRunId) next.groundingRunId = groundingRunId;
    if (policyEvaluationRunId) next.policyEvaluationRunId = policyEvaluationRunId;
    checkpointStore.save(next);
  }, [analysisV2RunId, caseId, groundingRunId, policyEvaluationRunId, retrievalRunId, visionRunId]);

  const activeSnapshotStatus = new Set(["QUEUED", "PENDING", "RUNNING", "RETRY_WAITING"]);
  const snapshotHasActiveSystemWork = [
    workflowSnapshotQuery.data?.analysis,
    workflowSnapshotQuery.data?.policy_retrieval,
    workflowSnapshotQuery.data?.grounded_explanation,
    workflowSnapshotQuery.data?.policy_evaluation,
    workflowSnapshotQuery.data?.resolution,
    workflowSnapshotQuery.data?.report,
  ].some((component) => component && activeSnapshotStatus.has(component.status));
  const snapshotShouldPoll = Boolean(
    running
    || snapshotHasActiveSystemWork
    || (!workflowSnapshotQuery.data && (
      analysisV2RunId
      || retrievalRunId
      || groundingRunId
      || policyEvaluationRunId
      || ["ANALYSIS_PENDING", "ANALYSIS_IN_PROGRESS"].includes(caseQuery.data?.status ?? "")
    )),
  );

  useEffect(() => {
    const snapshot = workflowSnapshotQuery.data;
    if (!snapshotShouldPoll || running || snapshotPaused || snapshot?.terminal) return;
    if (snapshotPollStartedAt.current === null) snapshotPollStartedAt.current = Date.now();
    const startedAt = snapshotPollStartedAt.current;
    if (workflowWaitExpired(startedAt, Date.now())) {
      setSnapshotTimedOut(true);
      setSnapshotPaused(true);
      return;
    }
    const delay = workflowPollDelay(snapshotPollAttempt.current);
    const timeoutId = window.setTimeout(() => {
      if (workflowWaitExpired(startedAt, Date.now(), DEFAULT_WORKFLOW_MAX_WAIT_MS)) {
        setSnapshotTimedOut(true);
        setSnapshotPaused(true);
        return;
      }
      snapshotPollAttempt.current += 1;
      void refetchWorkflowSnapshot();
    }, delay);
    return () => window.clearTimeout(timeoutId);
  }, [
    running,
    snapshotPaused,
    snapshotShouldPoll,
    workflowSnapshotQuery.data,
    workflowSnapshotQuery.data?.terminal,
    workflowSnapshotQuery.dataUpdatedAt,
    workflowSnapshotQuery.errorUpdatedAt,
    refetchWorkflowSnapshot,
  ]);

  useEffect(() => {
    const snapshot = workflowSnapshotQuery.data;
    if (!snapshot) return;
    const transitions: Array<[string, { run_id: string; status: string } | null, readonly unknown[]]> = [
      ["analysis", snapshot.analysis, ["analysis", caseId]],
      ["retrieval", snapshot.policy_retrieval, ["retrieval", caseId]],
      ["grounding", snapshot.grounded_explanation, ["grounding", caseId]],
      ["policy", snapshot.policy_evaluation, ["policy", caseId]],
      ["review", snapshot.review, ["case-reviews", caseId]],
      ["resolution", snapshot.resolution, ["resolution", caseId]],
      ["report", snapshot.report, ["report", caseId]],
    ];
    for (const [name, component, queryKey] of transitions) {
      if (!component) continue;
      const marker = `${name}:${component.run_id}:${component.status}`;
      if (observedSnapshotTransitions.current.has(marker)) continue;
      observedSnapshotTransitions.current.add(marker);
      const statusChangedToReadable = terminal.has(component.status)
        || name === "review" || name === "resolution" || name === "report";
      if (statusChangedToReadable) void queryClient.invalidateQueries({ queryKey });
    }
  }, [caseId, queryClient, workflowSnapshotQuery.data]);

  const evidenceMutation = useMutation({
    mutationFn: (file: File) => api.uploadEvidence(caseId, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["case", caseId] }),
  });

  function restartSnapshotPolling() {
    snapshotPollStartedAt.current = Date.now();
    snapshotPollAttempt.current = 0;
    setSnapshotTimedOut(false);
    setSnapshotPaused(false);
    void refetchWorkflowSnapshot();
  }

  async function startPolicyFlow() {
    if (!caseQuery.data) return;
    const recoveredCheckpoint = { ...checkpointStore.load(caseId) };
    if (analysisV2RunId) recoveredCheckpoint.analysisV2RunId = analysisV2RunId;
    if (visionRunId) recoveredCheckpoint.visionRunId = visionRunId;
    if (retrievalRunId) recoveredCheckpoint.retrievalRunId = retrievalRunId;
    if (groundingRunId) recoveredCheckpoint.groundingRunId = groundingRunId;
    if (policyEvaluationRunId) recoveredCheckpoint.policyEvaluationRunId = policyEvaluationRunId;
    checkpointStore.save(recoveredCheckpoint);
    restartSnapshotPolling();
    setRunning(true);
    setWorkflowError(null);
    setProgress([]);
    abortRef.current = new AbortController();
    try {
      await runPolicyWorkflow(api, caseId, policyAsOfDate(caseQuery.data.created_at), {
        signal: abortRef.current.signal,
        onProgress: (item) => setProgress((items) => {
          const next = items.filter((existing) => existing.stage !== item.stage);
          return [...next, item];
        }),
      });
      setCheckpoint(checkpointStore.load(caseId));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["analysis", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["analysis-runs", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["retrieval-runs", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["grounding-runs", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["policy-runs", caseId] }),
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
      restartSnapshotPolling();
    }
  }

  async function startVision() {
    setVisionError(null);
    let current = checkpointStore.load(caseId);
    if (analysisV2RunId && !current.analysisV2RunId) current = checkpointStore.patch(caseId, { analysisV2RunId });
    if (visionRunId && !current.visionRunId) current = checkpointStore.patch(caseId, { visionRunId });
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

  async function retryFailedText() {
    if (analysisQuery.data?.run.status !== "FAILED" || textRetrying) return;
    setTextRetrying(true);
    setWorkflowError(null);
    let current = resetFailedTextCheckpoint(checkpointStore.load(caseId));
    const key = newOpaqueKey();
    current = {
      ...current,
      idempotencyKeys: { ...current.idempotencyKeys, analysisV2: key },
    };
    checkpointStore.save(current);
    try {
      const started = await api.startAnalysis(
        caseId,
        "product_defect_text_extraction",
        "2.0.0",
        key,
      );
      current = checkpointStore.patch(caseId, { analysisV2RunId: started.analysis_run_id });
      setCheckpoint(current);
      await queryClient.invalidateQueries({ queryKey: ["analysis-runs", caseId] });
    } catch (cause) {
      setCheckpoint(checkpointStore.load(caseId));
      setWorkflowError(friendlyError(cause));
    } finally {
      setTextRetrying(false);
    }
  }

  async function retryFailedVision() {
    if (visionQuery.data?.run.status !== "FAILED" || visionRetrying) return;
    setVisionRetrying(true);
    setVisionError(null);
    let current = resetFailedVisionCheckpoint(checkpointStore.load(caseId));
    const key = newOpaqueKey();
    current = {
      ...current,
      idempotencyKeys: { ...current.idempotencyKeys, vision: key },
    };
    checkpointStore.save(current);
    try {
      const started = await api.startAnalysis(
        caseId,
        "product_defect_multimodal_analysis",
        "1.0.0",
        key,
      );
      current = checkpointStore.patch(caseId, { visionRunId: started.analysis_run_id });
      setCheckpoint(current);
      await queryClient.invalidateQueries({ queryKey: ["analysis-runs", caseId] });
    } catch (cause) {
      setCheckpoint(checkpointStore.load(caseId));
      setVisionError(friendlyError(cause));
    } finally {
      setVisionRetrying(false);
    }
  }

  function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) evidenceMutation.mutate(file);
    event.target.value = "";
  }

  if (caseQuery.isLoading) return <div className="page"><Loading label="문의 작업 공간을 준비하는 중" /></div>;
  if (caseQuery.error || !caseQuery.data) return <div className="page"><div className="error-panel" role="alert">{friendlyError(caseQuery.error)}</div></div>;
  const item = caseQuery.data;
  const review = policyEvaluationRunId
    ? reviewsQuery.data?.find((task) => task.policy_evaluation_run_id === policyEvaluationRunId)
    : undefined;
  const textRecoveryPending = !analysisV2RunId && analysisRunsQuery.isPending;
  const visionRecoveryPending = !visionRunId && analysisRunsQuery.isPending;
  const textRecoveryBlocked = !analysisV2RunId && analysisRunsQuery.isError;
  const visionRecoveryBlocked = !visionRunId && analysisRunsQuery.isError;
  const policyRecoveryPending = policyHistoryEnabled && (
    retrievalRunsQuery.isPending || groundingRunsQuery.isPending || policyRunsQuery.isPending
  );
  const policyRecoveryBlocked = policyHistoryEnabled && (
    retrievalRunsQuery.isError || groundingRunsQuery.isError || policyRunsQuery.isError
  );
  const recoveryBlocked = analysisRunsQuery.isError || policyRecoveryBlocked;
  const textRunFailed = analysisQuery.data?.run.status === "FAILED";
  const activePolicyRunStatus = [
    workflowSnapshotQuery.data?.policy_retrieval?.status ?? retrievalQuery.data?.run.status,
    workflowSnapshotQuery.data?.grounded_explanation?.status ?? groundingQuery.data?.run.status,
    workflowSnapshotQuery.data?.policy_evaluation?.status ?? policyQuery.data?.run.status,
  ].find((status) => status !== undefined && !terminal.has(status));
  const selectedEvidence = item.evidence.find(
    (evidence) => evidence.evidence_id === selectedEvidenceId,
  ) ?? item.evidence[0];
  const externalActionInput = item.attributes.external_action_input;
  const hasExternalActionInput = typeof externalActionInput === "object"
    && externalActionInput !== null
    && !Array.isArray(externalActionInput)
    && Object.keys(externalActionInput).length > 0;
  const guidanceLabel = policyGuidanceLabel(policyQuery.data?.run.summary_status, Boolean(review));
  const demoProvenance = readDemoProvenance(item.attributes);
  const isFictionalInquiryV2 = demoProvenance?.status === "VALID"
    && (demoProvenance.schemaVersion === "2.0" || demoProvenance.schemaVersion === "3.0");
  const demoImageObservation = readDemoImageObservation(item.attributes);
  const demoProduct = demoProductScenario(item.product_ref);
  const pocClosedSet = demoPocClosedSet(item.product_ref);
  const commerceContext = readSyntheticCommerceContext(item.attributes);
  const workflowDisabled = running || textRetrying || textRunFailed || textRecoveryPending
    || textRecoveryBlocked || policyRecoveryPending || policyRecoveryBlocked;
  const workflowLabel = running
    ? "분석 결과 확인 중…"
    : textRetrying
      ? "문의 분석 재시도 중…"
      : textRunFailed
        ? "문의 분석 재시도 필요"
        : textRecoveryPending || policyRecoveryPending
          ? "기존 결과 확인 중…"
          : activePolicyRunStatus
            ? "진행 상태 확인"
            : analysisV2RunId
              ? "분석 계속하기"
              : "문의 분석 시작";
  const reviewNeedsAction = Boolean(review && review.status !== "RESOLVED");
  const resolutionReady = Boolean(resolutionQuery.data);
  const focusTitle = reviewNeedsAction
    ? "담당자 검토를 진행해 주세요"
    : resolutionReady
      ? "결정 이후 처리 결과를 확인해 주세요"
      : textRunFailed
        ? "실패한 문의 분석을 다시 시작해 주세요"
        : policyEvaluationRunId
          ? "검토 작업이 준비되는 중입니다"
          : analysisV2RunId
            ? "정책 검토를 계속 진행해 주세요"
            : item.evidence.length === 0
              ? "결함을 확인할 사진이 필요합니다"
              : "문의 분석을 시작해 주세요";
  const focusDescription = reviewNeedsAction
    ? "AI와 정책 결과는 참고 자료입니다. 고객에게 적용할 최종 결정은 담당자가 직접 확인하고 기록합니다."
    : resolutionReady
      ? "담당자가 기록한 결정과 처리 사전 확인 결과를 확인할 수 있습니다. 실제 환불·교환 처리는 실행되지 않습니다."
      : textRunFailed
        ? "완료된 이미지 결과는 유지하고 실패한 문의 분석 단계만 새로 실행합니다."
        : policyEvaluationRunId
          ? "분석은 완료됐습니다. 현재 정책 결과와 연결된 담당자 검토 작업을 확인하고 있습니다."
          : analysisV2RunId
            ? "이미 완료된 단계는 다시 만들지 않고 남은 정책 검토 단계부터 확인합니다."
            : item.evidence.length === 0
              ? "사진을 추가하면 이미지 참고 분석과 정책 검토를 함께 진행할 수 있습니다."
              : "문의 내용과 첨부 사진을 확인한 뒤 정책 근거와 담당자 검토 작업을 준비합니다.";

  return <div className="page workspace-page">
    <PageHeader eyebrow={`문의 번호 · ${shortId(caseId)}`} title={commerceContext?.order.productDisplayName ?? demoProductDisplayName(item.product_ref) ?? `${operationalReference(item.product_ref)} 상품`} description={`주문 번호 ${item.order_ref} · 상품 번호 ${operationalReference(commerceContext?.order.sku ?? demoProduct?.syntheticSku ?? item.product_ref)} · ${formatDate(item.created_at)} 접수`}
      actions={<><Link className="button button-ghost" to="/cases"><ArrowLeft size={18} />목록</Link><StatusBadge status={item.status} /></>} />

    {recoveryBlocked && <div className="inline-alert inline-alert-danger run-recovery-alert" role="alert">
      <span>서버의 기존 분석·정책 실행을 확인하지 못했습니다. 중복 실행을 피하려면 먼저 다시 확인해 주세요.</span>
      <button className="button button-ghost button-small" type="button" onClick={() => {
        if (analysisRunsQuery.isError) void analysisRunsQuery.refetch();
        if (retrievalRunsQuery.isError) void retrievalRunsQuery.refetch();
        if (groundingRunsQuery.isError) void groundingRunsQuery.refetch();
        if (policyRunsQuery.isError) void policyRunsQuery.refetch();
      }}><RefreshCw size={14} />다시 확인</button>
    </div>}

    {(snapshotPaused || snapshotTimedOut || workflowSnapshotQuery.data?.degraded || workflowSnapshotQuery.data?.retry_at) && <Notice
      tone={workflowSnapshotQuery.data?.degraded || snapshotTimedOut ? "warning" : "info"}
      title={snapshotTimedOut ? "자동 상태 확인 시간이 끝났습니다" : snapshotPaused ? "상태 확인을 잠시 멈췄습니다" : "워크플로 상태 안내"}
    >
      <span>
        마지막 정상 단계 {workflowSnapshotQuery.data?.last_good ?? "확인 중"}
        {workflowSnapshotQuery.data?.retry_at ? ` · 다음 재시도 ${formatDate(workflowSnapshotQuery.data.retry_at)}` : ""}
        {workflowSnapshotQuery.data?.correlation_id ? ` · 추적 ID ${shortId(workflowSnapshotQuery.data.correlation_id)}` : ""}
      </span>
      <button className="button button-ghost button-small" type="button" onClick={restartSnapshotPolling}><RefreshCw size={14} />다시 확인</button>
    </Notice>}

    {snapshotShouldPoll && !snapshotPaused && <div className="workflow-poll-control">
      <span>한 개의 통합 상태 조회로 처리 진행을 확인하고 있습니다.</span>
      <button className="button button-ghost button-small" type="button" onClick={() => setSnapshotPaused(true)}>나중에 다시 열기</button>
    </div>}

    <section className="operator-focus" aria-labelledby="operator-focus-title" data-testid="operator-focus">
      <div className="operator-focus-copy">
        <p className="eyebrow">지금 할 일</p>
        <h2 id="operator-focus-title">{focusTitle}</h2>
        <p>{focusDescription}</p>
        <div className="operator-progress" aria-label="문의 처리 단계">
          <span className="operator-progress-done">문의 접수</span>
          <span className={item.evidence.length > 0 ? "operator-progress-done" : ""}>사진 확인</span>
          <span className={policyEvaluationRunId ? "operator-progress-done" : activePolicyRunStatus ? "operator-progress-active" : ""}>정책 검토</span>
          <span className={review?.status === "RESOLVED" ? "operator-progress-done" : review ? "operator-progress-active" : ""}>담당자 결정</span>
        </div>
      </div>
      <div className="operator-focus-action">
        {reviewNeedsAction && review
          ? <Link className="button button-primary button-large" to={`/reviews/${review.id}`}><ClipboardCheck size={18} />검토 진행하기</Link>
          : resolutionReady
            ? <a className="button button-primary button-large" href="#resolution-details"><ShieldCheck size={18} />처리 결과 보기</a>
            : textRunFailed
              ? <button className="button button-primary button-large" type="button" disabled={textRetrying} onClick={() => void retryFailedText()}><RefreshCw size={18} />문의 분석 다시 시작</button>
              : !analysisV2RunId && item.evidence.length === 0
                ? <a className="button button-primary button-large" href="#evidence-column-title"><ImagePlus size={18} />사진 추가하기</a>
                : <button className="button button-primary button-large" type="button" disabled={workflowDisabled} onClick={startPolicyFlow}><Play size={18} />{workflowLabel}</button>}
        <small>최종 결정은 담당자만 기록할 수 있습니다.</small>
      </div>
    </section>

    <div className="review-workbench" data-testid="review-workbench">
      <div className="case-context-stack">
      <section className="review-column inquiry-column" aria-labelledby="inquiry-column-title">
        <header className="review-column-header">
          <span className="review-step-number" aria-hidden="true">1</span>
          <div><h2 id="inquiry-column-title">문의 내용</h2><p>고객이 접수한 요청과 주문 정보</p></div>
          <div className="inquiry-header-badges">
            {isFictionalInquiryV2 && <span className="fictional-inquiry-badge" data-testid="fictional-inquiry-badge">온라인 접수</span>}
            <span className="request-pill">{businessLabel(item.requested_action)}</span>
          </div>
        </header>
        <p className="customer-message">{item.customer_message}</p>
        {commerceContext && <aside className="commerce-context-card" data-testid="commerce-context-card">
          <div className="commerce-context-heading">
            <div><span className="fictional-product-badge">고객 정보</span><h3>{commerceContext.customer.displayName}</h3><p>{commerceContext.customer.customerId} · {commerceContext.customer.membershipTier}</p></div>
            <strong>{formatCommerceMoney(commerceContext.order.paidAmount, commerceContext.order.currency)}</strong>
          </div>
          <div className="commerce-context-groups">
            <DefinitionList items={[
              { label: "연락처", value: commerceContext.customer.phoneMasked },
              { label: "구매 채널", value: commerceContext.order.salesChannel },
              { label: "판매자", value: commerceContext.order.sellerName },
              { label: "결제 수단", value: commerceContext.order.paymentMethodMasked },
            ]} />
            <DefinitionList items={[
              { label: "수령인", value: commerceContext.delivery.recipient },
              { label: "배송지", value: `[${commerceContext.delivery.postalCode}] ${commerceContext.delivery.addressLine1} ${commerceContext.delivery.addressLine2}` },
              { label: "배송사 / 운송장", value: `${commerceContext.delivery.carrier} · ${commerceContext.delivery.trackingNumberMasked}` },
              { label: "배송 완료", value: formatDate(commerceContext.delivery.deliveredAt) },
            ]} />
          </div>
          <small>화면 표시용 고객 정보이며 실제 고객 정보가 아닙니다.</small>
        </aside>}
        {demoProduct && <aside className="fictional-product-card" data-testid="fictional-product-card">
          <div className="fictional-product-heading">
            <div>
              <span className="fictional-product-badge">상품 정보</span>
              <h3>{demoProduct.displayName}</h3>
              <p>{demoProduct.productFamily}</p>
            </div>
            <strong>{formatSyntheticPriceBand(demoProduct)}</strong>
          </div>
          <DefinitionList items={[
            { label: "SKU", value: operationalReference(demoProduct.syntheticSku) },
            ...(pocClosedSet ? [
              { label: "상품군", value: pocClosedSet.productClassLabel },
              { label: "결함 시나리오", value: pocClosedSet.defectGroupLabels.length > 0 ? pocClosedSet.defectGroupLabels.join(" · ") : "지정 없음 · 저점수 참고" },
              { label: "데이터 사용 기준", value: `${pocClosedSet.admissionLabel} · ${pocClosedSet.admissionDescription}` },
            ] : []),
            { label: "문의 목적", value: demoProduct.inquiryPurpose },
            { label: "가격 기준", value: "화면 표시용 가격대 · 실제 판매가/환불 금액 아님" },
          ]} />
        </aside>}
        <DefinitionList items={[
          { label: "주문 번호", value: item.order_ref },
          { label: "상품 / SKU", value: operationalReference(commerceContext?.order.sku ?? demoProduct?.syntheticSku ?? item.product_ref) },
          { label: "접수 시각", value: formatDate(item.created_at) },
          { label: "첨부 이미지", value: `${item.evidence.length}장` },
        ]} />
        <details className="supporting-details inquiry-boundaries">
          <summary>시나리오 출처 및 입력 경계</summary>
          <DemoProvenance attributes={item.attributes} />
          <DefinitionList items={[
            { label: "외부 조치 입력", value: hasExternalActionInput ? "명시 입력 있음" : "명시 입력 없음" },
            { label: "추론 입력 금지", value: "금액·통화·수량·배송지는 문의에서 추정하지 않음" },
          ]} />
        </details>
      </section>

      <section className="review-column evidence-column" aria-labelledby="evidence-column-title">
        <header className="review-column-header">
          <span className="review-step-number" aria-hidden="true">2</span>
          <div><h2 id="evidence-column-title">이미지 근거</h2><p>고객이 첨부한 사진과 AI 참고 결과</p></div>
          <label className="button button-secondary button-small file-button"><ImagePlus size={16} />추가<input type="file" accept="image/jpeg,image/png,image/webp" onChange={upload} disabled={evidenceMutation.isPending} /></label>
        </header>
        {evidenceMutation.error && <div className="inline-alert inline-alert-danger" role="alert">{friendlyError(evidenceMutation.error)}</div>}
        {evidenceMutation.isPending && <Loading label="이미지를 안전하게 업로드하는 중" />}
        {item.evidence.length === 0 ? <EmptyState title="이미지가 없습니다"><span>이미지 기반 분석을 하려면 결함이 보이는 사진을 추가하세요.</span></EmptyState> : <>
          <div className="evidence-tabs" role="tablist" aria-label="첨부 이미지 선택">
            {item.evidence.map((evidence, index) => <button
              aria-controls={`evidence-panel-${evidence.evidence_id}`}
              aria-selected={selectedEvidence?.evidence_id === evidence.evidence_id}
              className={selectedEvidence?.evidence_id === evidence.evidence_id ? "evidence-tab-active" : ""}
              key={evidence.evidence_id}
              onClick={() => setSelectedEvidenceId(evidence.evidence_id)}
              role="tab"
              type="button"
            >{index + 1}</button>)}
          </div>
          {selectedEvidence && <div id={`evidence-panel-${selectedEvidence.evidence_id}`} role="tabpanel">
            <EvidencePreview caseId={caseId} evidence={selectedEvidence} />
          </div>}
        </>}
        {demoImageObservation && <aside className="image-observation-boundary" data-testid="image-observation-boundary">
          <ShieldCheck aria-hidden="true" size={16} />
          <div>
            <strong>사진에서 확인되는 범위</strong>
            <p>{demoImageObservation}</p>
            <small>배송 경위·작동·누수·구성 옵션 등 비가시 정보는 고객 진술이며 Vision 근거가 아닙니다.</small>
          </div>
        </aside>}
        <div className="column-section vision-section">
          <div className="column-section-heading"><div><Camera size={17} /><strong>이미지 참고 분석</strong></div><span>담당자 판단 보조</span></div>
          {visionError && <div className="inline-alert inline-alert-danger" role="alert">{visionError}</div>}
          {visionQuery.isLoading ? <Loading label="기존 Vision 실행을 불러오는 중" />
            : visionQuery.error ? <div className="inline-alert inline-alert-danger" role="alert">{friendlyError(visionQuery.error)}</div>
              : visionQuery.data ? <><VisionResult detail={visionQuery.data} />{visionQuery.data.run.status === "FAILED" && <div className="inline-alert inline-alert-danger failed-run-retry" role="alert">
                <span>Text·정책 결과는 보존하고 실패한 Vision 실행만 새 idempotency로 재시도합니다.</span>
                <button className="button button-ghost button-small" type="button" disabled={visionRetrying} onClick={() => void retryFailedVision()}><RefreshCw size={14} />{visionRetrying ? "재시도 중…" : "새 Vision 실행"}</button>
              </div>}</>
                : <button className="button button-secondary full-button" type="button" disabled={item.evidence.length === 0 || visionRecoveryPending || visionRecoveryBlocked} onClick={startVision}><Sparkles size={17} />{visionRecoveryPending ? "기존 실행 확인 중…" : "별도 Vision 실행"}</button>}
        </div>
      </section>
      </div>

      <section className="review-column policy-column" aria-labelledby="policy-column-title">
        <header className="review-column-header">
          <span className="review-step-number" aria-hidden="true">3</span>
          <div><h2 id="policy-column-title">정책 기반 권고</h2><p>적용 근거와 담당자가 확인할 사항</p></div>
          <ClipboardCheck size={20} className="muted-icon" />
        </header>
        <div className="policy-guidance-card" data-testid="policy-guidance">
          <span>현재 권고</span>
          {(groundingQuery.data?.citation_pack.citations.length ?? 0) === 0
            && <span className="synthetic-policy-badge">사내 정책 참고 자료</span>}
          <strong>{guidanceLabel}</strong>
          <p>정책 결과는 참고 권고입니다. 승인·반품·교환·환불은 담당자가 확인한 뒤 결정합니다.</p>
          {policyQuery.data?.run.summary_status && <StatusBadge status={policyQuery.data.run.summary_status} subtle />}
        </div>
        {workflowError && <div className="inline-alert inline-alert-danger" role="alert">{workflowError}</div>}
        {activePolicyRunStatus && <Notice tone="warning" title="서버의 진행 중 실행 복구"><span>{activePolicyRunStatus} 상태의 기존 실행을 이어서 확인하며 같은 단계의 새 실행은 만들지 않습니다.</span></Notice>}
        {textRunFailed && <div className="inline-alert inline-alert-danger" role="alert">문의 분석이 완료되지 않았습니다. 상단의 버튼으로 실패한 단계만 다시 시작해 주세요.</div>}
        <PolicyEvidence retrieval={retrievalQuery.data} grounding={groundingQuery.data} policy={policyQuery.data} />
        <div className="column-section review-section">
          <div className="column-section-heading"><div><ShieldCheck size={17} /><strong>사람 검토</strong></div>{review && <StatusBadge status={review.status} subtle />}</div>
          {review ? <div className="review-compact"><Notice tone="success" title="담당자 확인이 필요합니다"><span>정책과 이미지 분석은 판단을 돕는 참고 자료입니다. 최종 결정은 담당자가 근거를 확인하고 직접 기록합니다.</span></Notice><DefinitionList items={[
            { label: "검토 유형", value: review.task_type }, { label: "우선순위", value: review.priority },
          ]} /></div> : <div className="policy-empty-state"><strong>{policyEvaluationRunId ? "담당자 검토를 준비하고 있습니다" : "분석을 시작하면 검토 항목이 표시됩니다"}</strong><span>{policyEvaluationRunId ? "정책 결과와 연결된 검토 작업을 확인하고 있습니다." : "문의와 정책 근거를 확인한 후 담당자가 최종 결정을 기록합니다."}</span></div>}
        </div>
      </section>
    </div>

    <div className="workspace-support-stack">
      <details className="workspace-support-details">
        <summary><span><Activity size={18} />운영 정보 · 분석 진행과 실행 연결</span><small>실행 ID, 복구 상태, 상세 단계</small></summary>
        <div className="workspace-support-content">
          <Notice title="고정된 기본 경로"><span>Text v2 → RAW 질의 → HYBRID 검색 → Top-3 인용 → 근거 연결 → 정책 평가 순서입니다. Reranker와 LLM Query Builder는 사용하지 않습니다.</span></Notice>
          <Notice title="독립 실행 연결 경계"><span>Retrieval과 Grounding은 retrieval_run_id로 직접 연결됩니다. Policy 실행은 Text v2 analysis_run_id에만 독립 연결되고 Grounding FK가 없으므로, 여러 실행을 하나의 검증된 exact chain으로 단정하지 않습니다.</span></Notice>
          <div className="workflow-steps" data-testid="policy-workflow">
            <StepRow label="1. 문의 내용 구조화 (Text v2)" detail="문의 원문에서 요청·결함·누락 정보를 분리합니다." status={workflowSnapshotQuery.data?.analysis?.status ?? analysisQuery.data?.run.status ?? progress.find((p) => p.stage === "TEXT_V2")?.status ?? "PENDING"} />
            <StepRow label="2. RAW + HYBRID 정책 검색" detail="원문 기반으로 정책 조항 3개까지 찾습니다." status={workflowSnapshotQuery.data?.policy_retrieval?.status ?? retrievalQuery.data?.run.status ?? progress.find((p) => p.stage === "RAW_TOP3")?.status ?? "PENDING"} />
            <StepRow label="3. 인용과 설명 연결" detail="정책 문구가 설명을 실제로 뒷받침하는지 확인합니다." status={workflowSnapshotQuery.data?.grounded_explanation?.status ?? groundingQuery.data?.run.status ?? progress.find((p) => p.stage === "GROUNDING")?.status ?? "PENDING"} />
            <StepRow label="4. 정책 규칙 평가" detail="버전과 효력일이 고정된 규칙으로 검토 가이드를 만듭니다." status={workflowSnapshotQuery.data?.policy_evaluation?.status ?? policyQuery.data?.run.status ?? progress.find((p) => p.stage === "POLICY")?.status ?? "PENDING"} />
            <StepRow label="5. 사람 검토" detail="최종 결정은 담당자 또는 권한 있는 관리자가 내립니다." status={workflowSnapshotQuery.data?.review?.status ?? review?.status ?? progress.find((p) => p.stage === "REVIEW")?.status ?? "PENDING"} />
          </div>
          {analysisQuery.isLoading && <Loading label="기존 Text v2 실행을 불러오는 중" />}
          {analysisQuery.error && <div className="inline-alert inline-alert-danger" role="alert">{friendlyError(analysisQuery.error)}</div>}
          {analysisQuery.data && <div className="result-block text-analysis-summary" data-testid="text-analysis-summary">
            <div className="result-heading"><FileText size={18} /><strong>구조화 실행</strong><StatusBadge status={analysisQuery.data.run.status} subtle /></div>
            <DefinitionList items={[
              { label: "파이프라인", value: `Text v${analysisQuery.data.run.pipeline_version}` },
              { label: "실행 ID", value: shortId(analysisQuery.data.run.analysis_run_id) },
              { label: "기존 실행 복구", value: "서버 이력에서 최신 실행을 표시" },
            ]} />
          </div>}
          <PolicyExecutionDetails retrieval={retrievalQuery.data} grounding={groundingQuery.data} policy={policyQuery.data} />
        </div>
      </details>
      <details className="workspace-support-details resolution-details" id="resolution-details">
        <summary><span><ShieldCheck size={18} />결정 이후 · 처리 결과 확인</span><small>사람 결정 전에는 실행되지 않음</small></summary>
        <div className="workspace-support-content">
          <ResolutionPanel caseId={caseId} resolutionQuery={resolutionQuery} eventsQuery={eventsQuery} intentsQuery={intentsQuery} intentDetailQuery={intentDetailQuery} />
        </div>
      </details>
    </div>
  </div>;
}

function policyGuidanceLabel(summary: string | null | undefined, hasReview: boolean): string {
  if (hasReview) return "담당자 검토 필요";
  switch (summary) {
    case "REQUIRES_ADDITIONAL_EVIDENCE": return "추가 사진 또는 정보 필요";
    case "REQUIRES_HUMAN_REVIEW": return "담당자 검토 필요";
    case "BLOCKED_INPUT_INCOMPLETE": return "입력 정보 확인 필요";
    case "NO_APPLICABLE_RULE": return "담당자 직접 확인 필요";
    case "EVALUATED": return "정책 근거 확인 완료";
    default: return "분석 전";
  }
}

function PolicyEvidence({ retrieval, grounding, policy }: {
  retrieval: ReturnType<typeof api.getRetrieval> extends Promise<infer T> ? T | undefined : never;
  grounding: ReturnType<typeof api.getGrounding> extends Promise<infer T> ? T | undefined : never;
  policy: ReturnType<typeof api.getPolicy> extends Promise<infer T> ? T | undefined : never;
}) {
  if (!retrieval && !grounding && !policy) return null;
  const citations = grounding?.citation_pack.citations ?? [];
  const citationCount = grounding ? citations.length : retrieval?.hits.length ?? 0;
  return <div className="policy-evidence-summary">
    {grounding && <PolicyCitationList citations={citations} />}
    {!grounding && retrieval && <div className="policy-candidate-summary"><FileText size={17} /><span>정책 후보 {citationCount}개를 찾았습니다. 근거 연결이 완료되면 조항 본문을 표시합니다.</span></div>}
    {policy && <div className="policy-rule-summary"><CheckCircle2 size={17} /><div><strong>정책 규칙 {policy.rule_results.length}개 평가</strong><span>결과와 버전은 변경 불가 Review Packet에 고정됩니다.</span></div></div>}
  </div>;
}

function PolicyExecutionDetails({ retrieval, grounding, policy }: {
  retrieval: ReturnType<typeof api.getRetrieval> extends Promise<infer T> ? T | undefined : never;
  grounding: ReturnType<typeof api.getGrounding> extends Promise<infer T> ? T | undefined : never;
  policy: ReturnType<typeof api.getPolicy> extends Promise<infer T> ? T | undefined : never;
}) {
  if (!retrieval && !grounding && !policy) return null;
  const citationCount = grounding
    ? grounding.citation_pack.citations.length
    : retrieval?.hits.length ?? 0;
  return <div className="result-stack policy-execution-details">
    {retrieval && <div className="result-block"><div className="result-heading"><FileText size={18} /><strong>정책 후보 · 독립 Retrieval 실행</strong><span>{retrieval.hits.length}개</span></div><DefinitionList items={[
      { label: "Retrieval 실행 ID", value: shortId(retrieval.run.id) },
      { label: "Text v2 연결", value: shortId(retrieval.run.analysis_run_id) },
    ]} /><div className="chip-row"><span className="data-chip">RAW Query</span><span className="data-chip">{textValue(retrieval.retrieval_profile.base_mode ?? "HYBRID")}</span><span className="data-chip">Reranker Off</span><span className="data-chip">Top-{retrieval.run.top_k}</span></div>
      <ol className="citation-list">{retrieval.hits.slice(0, 3).map((hit, index) => <li key={String(hit.clause_id ?? index)}><strong>{String(hit.clause_id ?? `정책 조항 ${index + 1}`)}</strong><span>{String(hit.document_version ?? hit.document_id ?? "버전 정보 없음")}</span></li>)}</ol></div>}
    {grounding && <div className="result-block"><div className="result-heading"><ShieldCheck size={18} /><strong>근거 연결 · 독립 Grounding 실행</strong><StatusBadge status={grounding.run.status} subtle /></div><DefinitionList items={[
      { label: "Grounding 실행 ID", value: shortId(grounding.run.id) },
      { label: "Retrieval 직접 연결", value: shortId(grounding.run.retrieval_run_id) },
    ]} /><p>{citationCount}개 인용 근거 · 구조 검증 {grounding.structural_validation ? "기록됨" : "대기"}</p></div>}
    {policy && <div className="result-block"><div className="result-heading"><CheckCircle2 size={18} /><strong>정책 평가 · 독립 Policy 실행</strong><StatusBadge status={policy.run.status} subtle /></div><DefinitionList items={[
      { label: "Policy 실행 ID", value: shortId(policy.run.id) },
      { label: "Text v2 연결", value: shortId(policy.run.analysis_run_id) },
      { label: "Grounding 직접 FK", value: "제공되지 않음 · exact chain 미확정" },
    ]} /><div className="chip-row">{Object.entries(policy.input_qualification).map(([key, value]) => <span className="data-chip" key={key}>{key}: {value}</span>)}</div><p>{policy.rule_results.length}개 규칙 결과가 검토 패킷에 고정됩니다.</p></div>}
  </div>;
}

function VisionResult({ detail }: { detail: Awaited<ReturnType<typeof api.getAnalysis>> }) {
  const assessments = readBinaryVisionAssessments(detail.vision_results);
  return <div className="vision-result" data-testid="vision-result"><div className="result-heading"><Activity size={18} /><strong>이미지 이상 가능성</strong><StatusBadge status={detail.run.status} /></div>
    {assessments.map((assessment, index) => <div className="binary-assessment" data-testid="binary-vision-assessment" key={assessment.evidenceId ?? `assessment-${index}`}>
      <Notice tone={assessment.isCandidate ? "warning" : "info"} title={assessment.isCandidate ? "결함 가능성이 높게 감지되었습니다" : "결함 기준 미만이지만 정상 확정은 아닙니다"}>
        <span>사진 전체에서 이상 가능성을 확인한 참고 결과입니다. 결함 종류나 정확한 위치를 자동 확정하지 않습니다.</span>
      </Notice>
      <div className="assessment-score-card">
        <div><span>이상 가능성 점수</span><strong>{formatVisionProbability(assessment.score)}</strong></div>
        <progress aria-label="이상 후보 점수" max={1} value={assessment.score} />
        <small>참고 기준 {formatVisionProbability(assessment.threshold)} 이상</small>
      </div>
      <p className="vision-decision-boundary"><ShieldCheck size={15} />이 점수만으로 환불·교환을 결정하지 않습니다.</p>
      <details className="supporting-details vision-run-details"><summary>모델 및 검증 범위</summary>
        <span className={`vision-identity-badge ${assessment.isExactE3Identity ? "vision-identity-exact" : ""}`}>{assessment.isExactE3Identity ? "E3 Runtime identity 일치" : "일반 Binary Vision 계약"}</span>
        <p className="muted-copy">{assessment.qualification === "SYNTHETIC_MOCK"
          ? "현재 결과는 연결 확인용 참고 분석이며 실제 운영 모델 결과가 아닙니다."
          : assessment.qualification === "REMOTE_UNQUALIFIED"
            ? assessment.isExactE3Identity
              ? "고정된 E3 Runtime identity와 일치하지만 제품 적격성은 별도 external gate 증거로 확인해야 합니다."
              : `원격 Provider ${assessment.modelName ?? "identity 미상"}의 일반 Binary Vision 결과입니다. 이를 E3 결과로 해석할 수 없습니다.`
            : "Provider qualification을 확인할 수 없어 이 결과를 실제 E3 추론으로 해석할 수 없습니다."}</p>
        <DefinitionList items={[
        { label: "결과", value: assessment.isCandidate ? "HIGH_CONFIDENCE_DEFECT_CANDIDATE" : "BELOW_HIGH_CONFIDENCE_THRESHOLD" },
        { label: "검증 범위", value: describeVisionQualification(assessment.qualification) },
        { label: "파이프라인", value: `Multimodal v${detail.run.pipeline_version}` },
        { label: "실행 ID", value: shortId(detail.run.analysis_run_id) },
        { label: "Provider", value: assessment.providerName ?? "확인 불가" },
        { label: "모델", value: assessment.modelName ?? "확인 불가" },
      ]} /></details>
    </div>)}
    {assessments.length === 0 && <details className="supporting-details vision-run-details"><summary>모델 실행 정보</summary><DefinitionList items={[
      { label: "파이프라인", value: `Multimodal v${detail.run.pipeline_version}` },
      { label: "실행 ID", value: shortId(detail.run.analysis_run_id) },
      { label: "Vision 결과", value: detail.vision_results.length },
    ]} /></details>}
    {detail.vision_results.length > assessments.length && <Notice tone="warning" title="결과 계약 확인 필요"><span>일부 Vision 결과가 Binary 계약 identity 또는 비국소화 경계를 충족하지 못했습니다. nonempty detections와 image assessment가 공존하는 결과는 표시하지 않으며 결함 증거나 자동 결정 입력으로 사용하지 않습니다.</span></Notice>}
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
  return <Card title="최종 결정 · 처리 사전 확인" description="담당자 결정과 외부 시스템 반영 전 확인 결과는 문의 상태와 별도로 기록됩니다." className="spaced-card"
    actions={<button className="icon-button" type="button" aria-label="처리 결과 새로고침" onClick={() => { resolutionQuery.refetch(); eventsQuery.refetch(); intentsQuery.refetch(); intentDetailQuery.refetch(); }}><RefreshCw size={18} /></button>}>
    {resolutionQuery.isLoading ? <Loading label="처리 결과를 확인하는 중" /> : unavailable ? <EmptyState title="아직 처리 결과가 없습니다"><span>검토자가 최종 결정을 기록하면 안전한 처리 흐름이 시작됩니다.</span></EmptyState> : resolutionQuery.error ? <div className="inline-alert inline-alert-danger" role="alert">{friendlyError(resolutionQuery.error)}</div> : <>
      <div className="resolution-hero" data-testid="resolution-status"><span className="resolution-icon">{status === "ACTION_NEEDS_INPUT" ? <ShieldAlert /> : <ShieldCheck />}</span><div><p className="eyebrow">현재 단계</p><h3>{businessLabel(status ?? "DECISION_RECORDED")}</h3></div>{status && <StatusBadge status={status} />}</div>
      {status === "ACTION_NEEDS_INPUT" && <Notice tone="warning" title="외부 조치 입력이 부족합니다"><span>입력 보완 기능은 5C 범위에 포함되지 않습니다. Command·Attempt·Result를 만들지 않고 안전하게 보류합니다.</span></Notice>}
      <DefinitionList items={[
        { label: "결정 번호", value: textValue(resolutionQuery.data?.source_human_decision_id) },
        { label: "처리 요청", value: intent ? businessLabel(intent.action_type) : "0개" },
        { label: "사전 확인 시도", value: attempts },
        { label: "사전 확인 결과", value: results },
        { label: "실제 부작용", value: sideEffects ? "발생" : "없음" },
      ]} />
      {intent && <Notice tone="success" title="외부 시스템 미반영"><span>현재 단계는 외부 시스템에 연결하지 않고 요청 형식만 확인합니다. 실제 환불·교환 요청은 전송되지 않습니다.</span></Notice>}
      <div className="card-footer-actions"><span>변경 이력 {eventsQuery.data?.length ?? 0}건</span><Link className="button button-secondary" to={`/cases/${caseId}/report`}><FileText size={17} />최종 보고서</Link></div>
    </>}
  </Card>;
}
