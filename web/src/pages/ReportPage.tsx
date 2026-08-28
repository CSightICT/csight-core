import { ArrowLeft, LockKeyhole, Printer, ShieldCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError, api } from "../api/client";
import { Card, DefinitionList, EmptyState, Loading, Notice, PageHeader, formatDate, friendlyError, textValue } from "../components/Ui";
import { RefundConfirmation } from "../report/RefundConfirmation";
import { buildRefundDocument } from "../report/refundDocument";

export function ReportPage({ print = false }: { print?: boolean }) {
  const { caseId = "" } = useParams();
  const report = useQuery({ queryKey: ["report", caseId], queryFn: () => api.getReport(caseId), retry: false });
  const caseQuery = useQuery({ queryKey: ["case", caseId], queryFn: () => api.getCase(caseId), enabled: Boolean(caseId) });

  if (report.isLoading || caseQuery.isLoading) return <div className={print ? "print-report" : "page page-narrow"}><Loading label="고정된 보고서 스냅샷을 불러오는 중" /></div>;
  if (report.error instanceof ApiError && report.error.status === 404) return <div className="page page-narrow"><PageHeader title="최종 검토 보고서" actions={<Link className="button button-ghost" to={`/cases/${caseId}`}><ArrowLeft size={18} />케이스</Link>} /><EmptyState title="아직 최종 보고서가 없습니다"><span>Terminal Resolution에 도달하면 변경 불가능한 review_report/1.0.0 스냅샷이 생성됩니다.</span></EmptyState></div>;
  if (report.error || !report.data) return <div className="page"><div className="error-panel" role="alert">{friendlyError(report.error)}</div></div>;

  const data = report.data;
  const refundDocument = buildRefundDocument(data);
  const entries = Object.entries(data).filter(([key]) => !key.endsWith("_snapshot") && key !== "data_scope");
  const sections = [
    ["케이스 스냅샷", data.case_snapshot],
    ["분석 스냅샷", data.analysis_snapshot],
    ["정책 스냅샷", data.policy_snapshot],
    ["사람 검토 스냅샷", data.review_snapshot],
    ["Resolution 스냅샷", data.resolution_snapshot],
    ["DRY-RUN 스냅샷", data.dry_run_snapshot],
    ["Qualification 스냅샷", data.qualification_snapshot],
    ["데이터 범위", data.data_scope],
  ] as const;

  if (refundDocument.isRefund) return <div className={print ? "print-report" : "page refund-report-page"}>
    {!print && <PageHeader eyebrow="Immutable refund record" title="환불 처리 확인서" description="담당자 승인과 환불 DRY-RUN 결과를 실제 운영 문서 형식으로 정리했습니다."
      actions={<><Link className="button button-ghost" to={`/cases/${caseId}`}><ArrowLeft size={18} />케이스</Link><Link className="button button-primary" to={`/cases/${caseId}/report/print`}><Printer size={18} />인쇄 보기</Link></>} />}
    {print && <div className="refund-print-action print-hide"><button className="button button-primary" type="button" onClick={() => window.print()}><Printer size={18} />인쇄 / PDF 저장</button></div>}
    <RefundConfirmation document={refundDocument} />
  </div>;

  return <div className={print ? "print-report" : "page page-narrow"}>
    {!print && <PageHeader eyebrow="Immutable review report" title="최종 검토 보고서" description="Resolution 시점에 생성된 변경 불가능한 보고서입니다."
      actions={<><Link className="button button-ghost" to={`/cases/${caseId}`}><ArrowLeft size={18} />케이스</Link><Link className="button button-primary" to={`/cases/${caseId}/report/print`}><Printer size={18} />인쇄 보기</Link></>} />}
    {print && <header className="print-head"><div><p>CSight · FINAL REVIEW REPORT</p><h1>최종 검토 보고서</h1></div><button className="button print-hide" type="button" onClick={() => window.print()}><Printer size={18} />인쇄</button></header>}
    <Notice tone="success" title="무결성 고정 스냅샷"><span><LockKeyhole size={14} /> 이 보고서는 <strong>{textValue(data.schema_version ?? "review_report/1.0.0")}</strong> 계약으로 생성되었으며 기존 결정과 근거를 수정하지 않습니다.</span></Notice>
    <Card className="report-cover">
      <div className="report-title-row"><span className="report-seal"><ShieldCheck /></span><div><p className="eyebrow">Case</p><h2>{caseQuery.data?.order_ref ?? caseId}</h2><p>{caseQuery.data?.product_ref}</p></div></div>
      <DefinitionList items={entries.slice(0, 12).map(([label, value]) => ({ label, value: label.endsWith("_at") ? formatDate(String(value)) : textValue(value) }))} />
    </Card>
    {sections.filter(([, value]) => value !== undefined && value !== null).map(([title, value]) => <Card title={title} className="spaced-card report-section" key={title}><ReportValue value={value} /></Card>)}
    <footer className="report-footer">CSight 합성 데이터·Mock Vision 기반 PoC 콘솔 · 실제 외부 실행 없음</footer>
  </div>;
}

function ReportValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) return value.length ? <div className="report-list">{value.map((item, index) => <div key={index}><ReportValue value={item} /></div>)}</div> : <p>기록 없음</p>;
  if (value && typeof value === "object") return <DefinitionList items={Object.entries(value as Record<string, unknown>).map(([label, item]) => ({ label, value: item && typeof item === "object" ? <code className="inline-json">{JSON.stringify(item)}</code> : textValue(item) }))} />;
  return <p>{textValue(value)}</p>;
}
