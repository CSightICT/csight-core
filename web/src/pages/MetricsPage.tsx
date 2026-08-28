import { AlertTriangle, BarChart3, Clock3, FileWarning, FlaskConical, Gauge, ImageOff } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { ApiError, api } from "../api/client";
import type { PocSummary, RatioMetric } from "../api/contracts";
import { Card, EmptyState, Loading, Notice, PageHeader, friendlyError, textValue } from "../components/Ui";

type MetricKey = Exclude<keyof PocSummary, "schema_version" | "generated_at">;
const metricDefinitions: Array<{ key: MetricKey; title: string; description: string; icon: typeof Clock3; format?: "duration" | "rate" }> = [
  { key: "review_time", title: "실제 검토시간", description: "Claim 구간 합계", icon: Clock3, format: "duration" },
  { key: "recommendation_difference_rate", title: "권고와 다른 결정", description: "비교 가능한 결정 기준", icon: Gauge, format: "rate" },
  { key: "additional_evidence_request_rate", title: "추가자료 요청", description: "전체 검토 작업 기준", icon: FileWarning, format: "rate" },
  { key: "action_input_missing_rate", title: "처리 정보 누락", description: "조치 대상 결정 기준", icon: AlertTriangle, format: "rate" },
  { key: "dry_run_success_rate", title: "처리 사전 확인 성공", description: "완전한 처리 요청 기준", icon: FlaskConical, format: "rate" },
  { key: "analysis_failure_rate", title: "분석 실패", description: "전체 분석 실행 기준", icon: ImageOff, format: "rate" },
  { key: "analysis_partial_success_rate", title: "분석 부분 완료", description: "전체 분석 실행 기준", icon: ImageOff, format: "rate" },
];

function findMetric(data: PocSummary | undefined, key: MetricKey): RatioMetric | null {
  return data?.[key] ?? null;
}

export function MetricsPage() {
  const metrics = useQuery({ queryKey: ["poc-metrics"], queryFn: () => api.getMetrics(), retry: false });
  return <div className="page">
    <PageHeader eyebrow="운영 현황" title="상담 운영 지표" description="실제 관측값과 표본 크기를 함께 표시합니다. 사전 목표 절감률은 주장하지 않습니다." />
    <Notice tone="warning" title="해석 범위"><span>현재 지표는 운영 검증 전 내부 기록입니다. 실제 고객 성능이나 ROI 성과로 해석하지 마세요.</span></Notice>
    {metrics.isLoading ? <Loading label="운영 지표를 집계하는 중" /> : metrics.error instanceof ApiError && metrics.error.status === 404 ? <EmptyState title="지표 집계가 아직 준비되지 않았습니다"><span>첫 최종 처리와 분석 기록이 쌓이면 분자·분모·표본 수가 표시됩니다.</span></EmptyState> : metrics.error ? <div className="error-panel" role="alert">{friendlyError(metrics.error)}</div> : <>
      <div className="metric-grid">{metricDefinitions.map((definition) => <MetricCard key={definition.title} definition={definition} metric={findMetric(metrics.data, definition.key)} />)}</div>
      <Card title="집계 메타데이터" className="spaced-card"><div className="metadata-line"><BarChart3 size={19} /><span>생성 시각</span><strong>{textValue(metrics.data?.generated_at)}</strong></div></Card>
    </>}
  </div>;
}

function MetricCard({ definition, metric }: { definition: typeof metricDefinitions[number]; metric: RatioMetric | null }) {
  const Icon = definition.icon;
  const value = metric?.value;
  const display = value === undefined || value === null ? "—" : definition.format === "rate" ? `${(value <= 1 ? value * 100 : value).toFixed(1)}%` : `${(Number(value) / 60).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}분`;
  const numerator = metric?.numerator ?? 0;
  const denominator = metric?.denominator ?? 0;
  const sample = metric?.sample_count ?? denominator;
  return <Card className="metric-card"><div className="metric-title"><span><Icon size={20} /></span><div><h2>{definition.title}</h2><p>{definition.description}</p></div></div><strong className="metric-value">{display}</strong><div className="metric-fraction"><span>분자 <strong>{numerator}</strong></span><span>분모 <strong>{denominator}</strong></span><span>표본 <strong>{sample}</strong></span></div></Card>;
}
