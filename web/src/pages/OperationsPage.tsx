import { Activity, AlertTriangle, CheckCircle2, Clock3, RefreshCw, XCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";

import { api } from "../api/client";
import type { OperationsFailureSummary, OperationsProcessingSnapshot, OperationsQueueSnapshot } from "../api/contracts";
import { useAuth } from "../auth/AuthProvider";
import { Card, DefinitionList, Loading, Notice, PageHeader, formatDate, friendlyError } from "../components/Ui";

const labels: Record<string, string> = {
  analysis_dispatch: "모델 처리 요청",
  analysis: "문의·이미지 분석",
  policy_retrieval: "정책 검색",
  grounded_explanation: "정책 근거 설명",
  policy_evaluation: "정책 평가",
  human_review: "사람 검토",
  case_resolution: "결정 후 처리",
  action_simulation: "외부 처리 사전 확인",
};

const onboardingLabels: Record<string, string> = {
  ACTIVE_OPERATOR_STAFFING: "운영 담당자",
  SIGNED_INTAKE_SOURCE: "안전한 문의 접수",
  RETENTION_AUTOMATION: "개인정보 보존·삭제",
  OIDC_TENANT_MAPPING: "기업 로그인 연결",
  ACTIVE_POLICY_RUNTIME: "고객사 정책",
  PRIMARY_MODEL_ROUTES: "승인된 모델 경로",
};

const onboardingHelp: Record<string, { pass: string; fail: string }> = {
  ACTIVE_OPERATOR_STAFFING: { pass: "관리자와 검토 담당자가 준비됐습니다.", fail: "관리자와 검토 담당자를 각각 한 명 이상 활성화해 주세요." },
  SIGNED_INTAKE_SOURCE: { pass: "권한 없는 전용 연동 계정으로 문의를 받습니다.", fail: "서명된 문의 접수용 전용 연동 계정을 연결해 주세요." },
  RETENTION_AUTOMATION: { pass: "승인된 보존기간과 자동 삭제가 연결됐습니다.", fail: "고객사가 승인한 보존기간과 자동 삭제 대상을 설정해 주세요." },
  OIDC_TENANT_MAPPING: { pass: "기업 로그인 그룹이 고객사 권한에 연결됐습니다.", fail: "기업 로그인 그룹을 이 고객사의 역할에 연결해 주세요." },
  ACTIVE_POLICY_RUNTIME: { pass: "검색 인덱스와 현재 정책 규칙이 활성 상태입니다.", fail: "완전한 정책 인덱스와 현재 유효한 규칙을 활성화해 주세요." },
  PRIMARY_MODEL_ROUTES: { pass: "필수 모델 경로와 실행 보호가 모두 활성 상태입니다.", fail: "세 모델 작업의 승인 경로와 실행 보호를 모두 자격 검증해 주세요." },
};

function label(value: string): string {
  return labels[value] ?? value;
}

function age(seconds: number | null): string {
  if (seconds === null) return "대기 없음";
  if (seconds < 60) return `${seconds}초`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}분`;
  return `${Math.floor(seconds / 3600)}시간 ${Math.floor((seconds % 3600) / 60)}분`;
}

export function OperationsPage() {
  const { hasRole } = useAuth();
  const overview = useQuery({ queryKey: ["operations-overview"], queryFn: () => api.getOperationsOverview(), retry: false });
  const failures = useQuery({ queryKey: ["operations-failures", 24], queryFn: () => api.getOperationsFailures(24), retry: false });
  const readiness = useQuery({ queryKey: ["onboarding-readiness"], queryFn: () => api.getOnboardingReadiness(), retry: false });
  if (!hasRole("ADMIN")) return <Navigate to="/cases" replace />;
  const refresh = () => { void overview.refetch(); void failures.refetch(); void readiness.refetch(); };
  return <div className="page">
    <PageHeader eyebrow="관리자 전용" title="운영 상태" description="영속 작업 상태와 활성 버전을 한 화면에서 확인합니다."
      actions={<button className="button button-secondary" type="button" onClick={refresh}><RefreshCw size={17} />새로고침</button>} />
    {readiness.isLoading ? <Loading label="파일럿 시작 조건을 확인하는 중" /> : readiness.error ? <Notice tone="danger" title="파일럿 시작 조건을 확인할 수 없습니다"><span>{friendlyError(readiness.error)}</span></Notice> : readiness.data && <Card title="고객사 온보딩 준비도" description="여섯 조건이 모두 충족돼야 제한 운영 파일럿을 시작할 수 있습니다." className="spaced-card">
      <Notice tone={readiness.data.pilot_ready ? "success" : "warning"} title={readiness.data.pilot_ready ? "파일럿 시작 조건을 모두 충족했습니다" : "아직 파일럿을 시작할 수 없습니다"}>
        <span>{readiness.data.pilot_ready ? "실제 복원 훈련과 운영자 수동 점검을 포함한 최종 시작 절차를 진행하세요." : "실패한 항목을 먼저 완료하세요. 이 표시는 안전 관문을 우회하지 않습니다."}</span>
      </Notice>
      <div className="onboarding-gate-list">
        {readiness.data.gates.map((gate) => {
          const passed = gate.status === "PASS";
          const help = onboardingHelp[gate.code];
          return <div className={`onboarding-gate onboarding-gate-${passed ? "pass" : "fail"}`} key={gate.code}>
            {passed ? <CheckCircle2 aria-hidden="true" size={20} /> : <XCircle aria-hidden="true" size={20} />}
            <div><strong>{onboardingLabels[gate.code] ?? gate.code}</strong><span>{help ? (passed ? help.pass : help.fail) : gate.description}</span></div>
          </div>;
        })}
      </div>
    </Card>}
    <Notice tone="warning" title="현재 관측 범위"><span>이 화면은 데이터베이스에 기록된 상태를 보여줍니다. RabbitMQ·MinIO·모델 노드의 직접 상태, 분산 추적, 알림 전달은 아직 파일럿 자격 증거가 아닙니다.</span></Notice>
    {overview.isLoading ? <Loading label="운영 상태를 집계하는 중" /> : overview.error ? <div className="error-panel" role="alert">{friendlyError(overview.error)}</div> : overview.data && <>
      <div className="operations-summary-grid">
        <Card className="operations-summary"><Activity /><span>전체 대기</span><strong>{overview.data.total_backlog_count}</strong></Card>
        <Card className="operations-summary"><AlertTriangle /><span>정체</span><strong>{overview.data.total_stalled_count}</strong></Card>
        <Card className="operations-summary"><Clock3 /><span>집계 시각</span><strong>{formatDate(overview.data.generated_at)}</strong></Card>
      </div>
      <section className="operations-section" aria-labelledby="queue-health-title"><h2 id="queue-health-title">처리선 대기 상태</h2><div className="operations-card-grid">{overview.data.queues.map((queue) => <QueueCard key={queue.queue} queue={queue} />)}</div></section>
      <section className="operations-section" aria-labelledby="component-health-title"><h2 id="component-health-title">단계별 처리 상태</h2><div className="operations-card-grid">{overview.data.processing.map((component) => <ComponentCard key={component.component} component={component} />)}</div></section>
      <Card title="활성·최근 관측 버전" description="최근 실행 스냅샷은 활성 배포 확정이 아니라 관측값입니다." className="spaced-card">
        <div className="operations-version-list">{overview.data.active_versions.map((version) => <div key={`${version.kind}:${version.component}:${version.name}:${version.version}`}><span>{label(version.component)} · {version.kind}</span><strong>{version.name} / {version.version}</strong><small>{version.source} · {formatDate(version.observed_at)}</small></div>)}</div>
      </Card>
    </>}
    {failures.data && <Card title="최근 24시간 실패 신호" description={`실패 ${failures.data.total_failed_count} · 부분 성공 ${failures.data.total_partial_success_count} · 재시도 ${failures.data.total_retry_count} · 정체 ${failures.data.total_stalled_count}`} className="spaced-card">
      <div className="operations-card-grid">{failures.data.components.map((component) => <FailureCard key={component.component} component={component} />)}</div>
    </Card>}
  </div>;
}

function QueueCard({ queue }: { queue: OperationsQueueSnapshot }) {
  return <Card title={label(queue.queue)} className={queue.stalled_count > 0 || queue.failed_count > 0 ? "operations-risk-card" : ""}><DefinitionList items={[
    { label: "대기", value: queue.backlog_count }, { label: "최고 대기시간", value: age(queue.oldest_backlog_age_seconds) },
    { label: "처리 중", value: queue.processing_count }, { label: "재시도", value: queue.retry_count },
    { label: "실패 / 정체", value: `${queue.failed_count} / ${queue.stalled_count}` }, { label: "마지막 정상", value: formatDate(queue.last_healthy_at) },
  ]} /></Card>;
}

function ComponentCard({ component }: { component: OperationsProcessingSnapshot }) {
  return <Card title={label(component.component)}><DefinitionList items={[
    { label: "대기 / 실행", value: `${component.backlog_count} / ${component.running_count}` },
    { label: "최고 대기시간", value: age(component.oldest_backlog_age_seconds) },
    { label: "부분 성공", value: component.partial_success_count }, { label: "실패", value: component.failed_count },
    { label: "재시도 / 정체", value: `${component.retry_count} / ${component.stalled_count}` },
    { label: "마지막 정상", value: formatDate(component.last_healthy_at) },
  ]} /></Card>;
}

function FailureCard({ component }: { component: OperationsFailureSummary }) {
  return <div className="operations-failure"><div><AlertTriangle size={17} /><strong>{label(component.component)}</strong></div><span>실패 {component.failed_count} · 부분 성공 {component.partial_success_count} · 정체 {component.stalled_count}</span><small>{component.top_failure_codes.length ? component.top_failure_codes.map((item) => `${item.code} ${item.count}`).join(" · ") : "기록된 실패 코드 없음"}</small></div>;
}
