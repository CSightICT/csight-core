import { Database, LockKeyhole, ShieldCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { Card, EmptyState, Loading, PageHeader, formatDate, friendlyError, shortId } from "../components/Ui";
import { businessLabel } from "../presentation/businessLabels";

export function DataAssetsPage() {
  const summary = useQuery({ queryKey: ["data-assets"], queryFn: api.getDataAssetSummary });
  if (summary.isLoading) return <div className="page"><Loading label="고객사 데이터 자산 현황을 불러오는 중" /></div>;
  if (summary.error || !summary.data) return <div className="page"><div className="error-panel" role="alert">{friendlyError(summary.error)}</div></div>;
  const data = summary.data;
  return <div className="page data-assets-page">
    <PageHeader eyebrow="우리 팀의 처리 경험" title="데이터 자산" description="처리한 문의와 담당자의 판단이 쌓여, 다음 업무를 돌아볼 수 있는 기록이 됩니다." />
    <div className="data-asset-hero">
      <Card><span className="asset-label">쌓인 처리 기록</span><div className="asset-count"><Database aria-hidden="true" /><span><strong>{data.total_records.toLocaleString("ko-KR")}</strong>건</span></div><p>담당자가 처리한 결과를 자동으로 모아 보관합니다.</p><small>시연·미확인 기록 포함</small></Card>
      <Card><span className="asset-label">실제 운영 분석에 쓸 수 있는 기록</span><div className="asset-count"><ShieldCheck aria-hidden="true" /><span><strong>{data.eligible_records.toLocaleString("ko-KR")}</strong>건</span></div><p>실운영 출처가 확인된 기록만 따로 집계합니다.</p><small>나머지 {data.excluded_records.toLocaleString("ko-KR")}건은 분석 대상에서 제외</small></Card>
    </div>
    <Card className="asset-value" title="처리할수록 우리 팀의 사례가 쌓입니다">
      <div className="asset-value-steps"><div><strong>1. 처리 결과 보관</strong><p>담당자가 확정한 판단을 기록합니다.</p></div><div><strong>2. 지난 사례 확인</strong><p>최근 기록에서 당시의 처리 보고서를 엽니다.</p></div><div><strong>3. 개선할 부분 살피기</strong><p>결정·처리 결과를 모아 업무를 돌아봅니다.</p></div></div>
      <p className="muted-copy">문의 원문과 직접 식별정보는 이 자산 기록에서 제외합니다.</p>
    </Card>
    <Card title="최근 처리 사례" description="실운영 출처가 확인된 기록입니다. 선택하면 처리 보고서를 볼 수 있습니다.">
      {!data.recent_records.length ? <EmptyState title="아직 표시할 실운영 사례가 없습니다"><span>실운영 출처가 확인된 문의를 최종 처리하면 이곳에 쌓입니다. 시연·미확인 기록은 포함하지 않습니다.</span></EmptyState> : <div className="asset-records">{data.recent_records.map((record) => <Link to={`/cases/${record.case_id}/report`} key={record.asset_id}><span><LockKeyhole size={15} />문의 번호 {shortId(record.case_id)}</span><strong>{businessLabel(record.label_snapshot.human_decision)}</strong><small>{formatDate(record.created_at)}</small></Link>)}</div>}
    </Card>
    <details className="supporting-details asset-details"><summary>처리 현황과 관리 정보 자세히 보기</summary>
      <div className="asset-distributions">
        <Distribution title="담당자의 판단" values={data.decision_distribution} />
        <Distribution title="처리 결과" values={data.resolution_distribution} />
        <Distribution title="상품별 기록" values={data.product_distribution} />
      </div>
      <p>{data.drift_evaluation_available ? "기간별 변화 비교를 위한 표본이 준비되었습니다." : "기간별 변화를 비교하기 위한 기록을 모으고 있습니다."} 모델 학습이나 성능 향상을 의미하지는 않습니다.</p>
      <p className="muted-copy">기준 기록 {data.baseline_minimum}건 · 변화 비교 기준 {data.drift_review_minimum}건 · 현재 상태: {businessLabel(data.readiness_status)}</p>
      <div className="asset-distributions"><Distribution title="분석 모델 버전" values={data.model_version_distribution} /><Distribution title="적용 정책 버전" values={data.policy_version_distribution} /></div>
    </details>
  </div>;
}

function Distribution({ title, values }: { title: string; values: Record<string, number> }) {
  const entries = Object.entries(values);
  return <Card title={title}>{entries.length ? <ul className="distribution-list">{entries.slice(0, 8).map(([label, count]) => <li key={label}><span>{businessLabel(label)}</span><strong>{count}건</strong></li>)}</ul> : <p className="muted-copy">아직 기록이 없습니다</p>}</Card>;
}
