import { Database, LockKeyhole, ShieldCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { Card, EmptyState, Loading, Notice, PageHeader, formatDate, friendlyError, shortId } from "../components/Ui";
import { businessLabel } from "../presentation/businessLabels";

export function DataAssetsPage() {
  const summary = useQuery({ queryKey: ["data-assets"], queryFn: api.getDataAssetSummary });
  if (summary.isLoading) return <div className="page"><Loading label="고객사 데이터 자산 현황을 불러오는 중" /></div>;
  if (summary.error || !summary.data) return <div className="page"><div className="error-panel" role="alert">{friendlyError(summary.error)}</div></div>;
  const data = summary.data;
  const progressTarget = data.eligible_records < data.baseline_minimum ? data.baseline_minimum : data.drift_review_minimum;
  const progress = Math.min(100, Math.round((data.eligible_records / progressTarget) * 100));
  return <div className="page data-assets-page">
    <PageHeader eyebrow="고객사 학습 원장" title="데이터 자산" description="처리 결과를 고객사별로 축적해 모델·정책 분포 변화의 기준선을 준비합니다." />
    <Notice tone="success" title="비식별 · 변경 불가 · 출처 분리"><span>문의 원문과 직접 식별정보는 제외합니다. 파일럿 실운영으로 확인된 기록만 준비도에 포함하고 합성·미확인 기록은 별도로 보관합니다.</span></Notice>
    <div className="data-asset-hero">
      <Card><div className="asset-count"><Database /><span><strong>{data.eligible_records}</strong>건</span></div><p>{businessLabel(data.readiness_status)}</p><div className="asset-progress"><span style={{ width: `${progress}%` }} /></div><small>파일럿 대상 {data.eligible_records}건 · 제외 {data.excluded_records}건 · 전체 {data.total_records}건</small></Card>
      <Card><div className="asset-safety"><ShieldCheck /><div><strong>{data.drift_evaluation_available ? "드리프트 점검 가능" : "성능 수치 판단 보류"}</strong><p>{data.drift_evaluation_available ? "두 구간의 분포를 비교할 표본이 준비되었습니다." : "표본이 충분해질 때까지 드리프트 수치를 만들지 않습니다."}</p></div></div></Card>
    </div>
    <div className="asset-distributions">
      <Distribution title="담당자 결정" values={data.decision_distribution} />
      <Distribution title="처리 결과" values={data.resolution_distribution} />
      <Distribution title="상품 분포" values={data.product_distribution} />
      <Distribution title="비전 모델 버전" values={data.model_version_distribution} />
      <Distribution title="정책 버전" values={data.policy_version_distribution} />
    </div>
    <Card title="최근 파일럿 적재 기록" description="출처가 확인된 파일럿 실운영 기록만 표시합니다.">
      {!data.recent_records.length ? <EmptyState title="아직 적재된 기록이 없습니다"><span>새 문의를 담당자가 최종 처리하면 첫 데이터 자산이 자동 생성됩니다.</span></EmptyState> : <div className="asset-records">{data.recent_records.map((record) => <Link to={`/cases/${record.case_id}/report`} key={record.asset_id}><span><LockKeyhole size={15} />문의 번호 {shortId(record.case_id)}</span><strong>{businessLabel(record.label_snapshot.human_decision)}</strong><small>{formatDate(record.created_at)}</small></Link>)}</div>}
    </Card>
  </div>;
}

function Distribution({ title, values }: { title: string; values: Record<string, number> }) {
  const entries = Object.entries(values);
  return <Card title={title}>{entries.length ? <ul className="distribution-list">{entries.slice(0, 8).map(([label, count]) => <li key={label}><span>{businessLabel(label)}</span><strong>{count}건</strong></li>)}</ul> : <p className="muted-copy">표본 없음</p>}</Card>;
}
