import { ArrowLeft, LockKeyhole, Printer, ShieldCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError, api } from "../api/client";
import { Card, DefinitionList, EmptyState, Loading, Notice, PageHeader, formatDate, friendlyError, textValue } from "../components/Ui";
import { RefundConfirmation } from "../report/RefundConfirmation";
import { CommunicationSimulationPanel } from "../report/CommunicationSimulationPanel";
import { buildRefundDocument } from "../report/refundDocument";
import { businessLabel, fieldLabel, operationalReference } from "../presentation/businessLabels";

export function ReportPage({ print = false }: { print?: boolean }) {
  const { caseId = "" } = useParams();
  const report = useQuery({ queryKey: ["report", caseId], queryFn: () => api.getReport(caseId), retry: false });
  const caseQuery = useQuery({ queryKey: ["case", caseId], queryFn: () => api.getCase(caseId), enabled: Boolean(caseId) });

  if (report.isLoading || caseQuery.isLoading) return <div className={print ? "print-report" : "page page-narrow"}><Loading label="고정된 보고서 스냅샷을 불러오는 중" /></div>;
  if (report.error instanceof ApiError && report.error.status === 404) return <div className="page page-narrow"><PageHeader title="최종 검토 보고서" actions={<Link className="button button-ghost" to={`/cases/${caseId}`}><ArrowLeft size={18} />문의</Link>} /><EmptyState title="아직 최종 보고서가 없습니다"><span>최종 처리 단계에 도달하면 변경 불가능한 검토 보고서 스냅샷이 생성됩니다.</span></EmptyState></div>;
  if (report.error || !report.data) return <div className="page"><div className="error-panel" role="alert">{friendlyError(report.error)}</div></div>;

  const data = report.data;
  const refundDocument = buildRefundDocument(data);
  const entries = Object.entries(data).filter(([key]) => !key.endsWith("_snapshot") && key !== "data_scope");
  const sections = [
    ["문의 스냅샷", data.case_snapshot],
    ["분석 스냅샷", data.analysis_snapshot],
    ["정책 스냅샷", data.policy_snapshot],
    ["사람 검토 스냅샷", data.review_snapshot],
    ["처리 결과 스냅샷", data.resolution_snapshot],
    ["처리 사전 확인 기록", data.dry_run_snapshot],
    ["검증 정보 스냅샷", data.qualification_snapshot],
    ["데이터 범위", data.data_scope],
  ] as const;

  if (refundDocument.isRefund) return <div className={print ? "print-report" : "page refund-report-page"}>
    {!print && <PageHeader eyebrow="변경 불가 환불 기록" title="환불 처리 확인서" description="담당자 승인과 외부 시스템 반영 전 확인 결과를 실제 운영 문서 형식으로 정리했습니다."
      actions={<><Link className="button button-ghost" to={`/cases/${caseId}`}><ArrowLeft size={18} />문의</Link><Link className="button button-primary" to={`/cases/${caseId}/report/print`}><Printer size={18} />인쇄 보기</Link></>} />}
    {print && <div className="refund-print-action print-hide"><button className="button button-primary" type="button" onClick={() => window.print()}><Printer size={18} />인쇄 / PDF 저장</button></div>}
    {!print && <CommunicationSimulationPanel caseId={caseId} />}
    <RefundConfirmation document={refundDocument} />
  </div>;

  return <div className={print ? "print-report" : "page page-narrow"}>
    {!print && <PageHeader eyebrow="변경 불가 검토 기록" title="최종 검토 보고서" description="최종 처리 시점에 생성된 변경 불가능한 보고서입니다."
      actions={<><Link className="button button-ghost" to={`/cases/${caseId}`}><ArrowLeft size={18} />문의</Link><Link className="button button-primary" to={`/cases/${caseId}/report/print`}><Printer size={18} />인쇄 보기</Link></>} />}
    {print && <header className="print-head"><div><p>CSight · 최종 검토 보고서</p><h1>최종 검토 보고서</h1></div><button className="button print-hide" type="button" onClick={() => window.print()}><Printer size={18} />인쇄</button></header>}
    <Notice tone="success" title="무결성 고정 스냅샷"><span><LockKeyhole size={14} /> 이 보고서는 <strong>{textValue(data.schema_version ?? "review_report/1.0.0")}</strong> 계약으로 생성되었으며 기존 결정과 근거를 수정하지 않습니다.</span></Notice>
    <Card className="report-cover">
      <div className="report-title-row"><span className="report-seal"><ShieldCheck /></span><div><p className="eyebrow">문의</p><h2>{caseQuery.data?.order_ref ?? caseId}</h2><p>{operationalReference(caseQuery.data?.product_ref ?? "상품 번호 미기록")}</p></div></div>
      <DefinitionList items={entries.slice(0, 12).map(([label, value]) => ({ label: fieldLabel(label), value: label.endsWith("_at") ? formatDate(String(value)) : reportPrimitive(value) }))} />
    </Card>
    {sections.filter(([, value]) => value !== undefined && value !== null).map(([title, value]) => <Card title={title} className="spaced-card report-section" key={title}><ReportValue value={value} /></Card>)}
    <footer className="report-footer">CSight 상담 처리 지원 기록 · 외부 시스템 미반영</footer>
  </div>;
}

function ReportValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) return value.length ? <div className="report-list">{value.map((item, index) => <div key={index}><ReportValue value={item} /></div>)}</div> : <p>기록 없음</p>;
  if (value && typeof value === "object") return <DefinitionList items={Object.entries(value as Record<string, unknown>).map(([label, item]) => ({ label: fieldLabel(label), value: item && typeof item === "object" ? <ReportValue value={item} /> : reportPrimitive(item) }))} />;
  return <p>{reportPrimitive(value)}</p>;
}

function reportPrimitive(value: unknown): string {
  if (typeof value === "string") return businessLabel(value);
  return textValue(value);
}
