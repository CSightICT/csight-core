import { CircleDollarSign, FileCheck2, LockKeyhole, PackageCheck, ShieldCheck } from "lucide-react";

import { formatDate, shortId } from "../components/Ui";
import type { RefundDocumentModel } from "./refundDocument";

const fieldLabels: Record<string, string> = {
  amount: "환불 금액",
  currency: "통화",
  quantity: "수량",
  order_ref: "주문번호",
  product_ref: "상품번호",
  shipping_address_ref: "배송지 참조",
};

function fieldList(fields: string[]): string {
  return fields.length ? fields.map((field) => fieldLabels[field] ?? field).join(", ") : "없음";
}

function AuditValue({ children }: { children: string }) {
  return <span className="refund-audit-value" title={children}>{shortId(children)}</span>;
}

export function RefundConfirmation({ document }: { document: RefundDocumentModel }) {
  const incomplete = document.status === "needs-input";

  return <article className="refund-document" data-testid="refund-confirmation">
    <header className="refund-document-head">
      <div className="refund-document-brand">
        <span className="refund-document-mark"><CircleDollarSign aria-hidden="true" /></span>
        <div><strong>CSight Commerce</strong><small>고객 운영 지원</small></div>
      </div>
      <div className="refund-document-heading">
        <p>환불 처리 기록</p>
        <h2>환불 처리 확인서</h2>
      </div>
      <dl className="refund-document-number">
        <div><dt>문서번호</dt><dd>{document.documentNumber}</dd></div>
        <div><dt>생성일시</dt><dd>{formatDate(document.generatedAt)}</dd></div>
      </dl>
    </header>

    <div className="refund-simulation-ribbon">
      <ShieldCheck aria-hidden="true" size={17} />
      <strong>외부 처리 전 확인 문서</strong>
      <span>외부 결제사 전송 없음 · 실제 환불 미실행</span>
    </div>

    <section className={`refund-summary refund-summary-${document.status}`} aria-label="환불 처리 요약">
      <div className="refund-summary-amount">
        <span>환불 예정 금액</span>
        <strong>{document.amountLabel}</strong>
        <small>{document.quantityLabel} · 입력값 기준</small>
      </div>
      <div className="refund-summary-status">
        <span className={`refund-state refund-state-${document.status}`}>{document.statusLabel}</span>
        <strong>실제 환불 상태: 미실행</strong>
        <small>{document.refundMethodLabel}</small>
      </div>
    </section>

    {incomplete && <div className="refund-attention" role="status">
      <strong>환불 요청을 생성하지 않았습니다.</strong>
      <span>필수 정보가 부족합니다: {fieldList(document.missingFields)}. 값을 추정하거나 기본값으로 채우지 않고 담당자 확인을 기다립니다.</span>
    </div>}

    <section className="refund-document-section">
      <header><span>01</span><div><h3>주문 및 환불 신청 정보</h3><p>고정된 케이스 기록</p></div></header>
      <dl className="refund-field-grid">
        <div><dt>주문번호</dt><dd>{document.orderRef}</dd></div>
        <div><dt>상품명</dt><dd>{document.productName}</dd></div>
        <div><dt>상품번호 / SKU</dt><dd>{document.syntheticSku}</dd></div>
        <div><dt>판매 채널 / 판매자</dt><dd>{document.salesChannel} · {document.sellerName}</dd></div>
        <div><dt>신청 유형</dt><dd>상품 하자 환불</dd></div>
        <div><dt>환불 수량</dt><dd>{document.quantityLabel}</dd></div>
        <div className="refund-field-wide"><dt>환불 사유 및 승인 근거</dt><dd>{document.refundReason}</dd></div>
      </dl>
    </section>

    <section className="refund-document-section">
      <header><span>02</span><div><h3>고객 및 배송 정보</h3><p>합성 고객 스냅샷 · 직접 연락 불가</p></div></header>
      <dl className="refund-field-grid">
        <div><dt>고객명</dt><dd>{document.customerName}</dd></div>
        <div><dt>Customer ID</dt><dd>{document.customerId}</dd></div>
        <div><dt>마스킹 연락처</dt><dd>{document.customerPhone}</dd></div>
        <div><dt>멤버십</dt><dd>{document.membershipTier}</dd></div>
        <div><dt>수령인 / 연락처</dt><dd>{document.recipient} · {document.deliveryPhone}</dd></div>
        <div><dt>배송사 / 운송장</dt><dd>{document.carrierAndTracking}</dd></div>
        <div className="refund-field-wide"><dt>배송지</dt><dd>{document.shippingAddress}</dd></div>
      </dl>
      {document.syntheticCommerceContext && <p className="refund-synthetic-note">화면 표시용 정보이며 실제 고객 데이터가 아닙니다.</p>}
    </section>

    <section className="refund-document-section">
      <header><span>03</span><div><h3>환불 처리 내역</h3><p>결제·반품 시스템 연동 전 확인 항목</p></div></header>
      <table className="refund-processing-table">
        <tbody>
          <tr><th>담당자 결정</th><td>{document.decisionType}</td><th>처리 상태</th><td>{document.statusLabel}</td></tr>
          <tr><th>원 결제 금액</th><td>{document.paidAmountLabel}</td><th>환불 예정 금액</th><td>{document.amountLabel}</td></tr>
          <tr><th>결제 수단</th><td>{document.paymentMethod}</td><th>환급 경로</th><td>{document.refundMethodLabel}</td></tr>
          <tr><th>결제업자 취소 요청</th><td>미요청 · 외부 시스템 미연결</td><th>고객 통지</th><td>실제 발송 없음</td></tr>
          <tr><th>반품 승인번호</th><td>외부 시스템 미연동</td><th>회수 / 추적 정보</th><td>보고서 스냅샷에 기록 없음</td></tr>
          <tr><th>처리 예정일</th><td colSpan={3}>외부 결제수단 및 회수 조건 확정 후 산정</td></tr>
        </tbody>
      </table>
    </section>

    <section className="refund-document-section">
      <header><span>04</span><div><h3>처리 이력</h3><p>사람 승인과 시스템 검증을 구분한 감사 기록</p></div></header>
      <ol className="refund-timeline">
        <li><span><PackageCheck aria-hidden="true" /></span><div><strong>환불 문의 접수</strong><p>{formatDate(document.requestedAt)}</p></div></li>
        <li><span><FileCheck2 aria-hidden="true" /></span><div><strong>인증된 담당자 결정 기록</strong><p>{formatDate(document.approvedAt)}</p></div></li>
        <li><span><ShieldCheck aria-hidden="true" /></span><div><strong>{incomplete ? "외부 요청 생성 보류" : "외부 요청 사전 확인"}</strong><p>{formatDate(document.validatedAt)}</p></div></li>
      </ol>
    </section>

    <section className="refund-document-section refund-approval-section">
      <header><span>05</span><div><h3>정책 근거 및 승인</h3><p>모델 권고가 아닌 사람의 최종 결정</p></div></header>
      <div className="refund-approval-grid">
        <dl>
          <div><dt>적용 정책</dt><dd>{document.policyReference}</dd></div>
          <div><dt>정책 기준일</dt><dd>{document.policyAsOfDate}</dd></div>
          <div><dt>담당자 ID</dt><dd>{document.reviewer}</dd></div>
        </dl>
        <div className="refund-signature">
          <span>담당자 승인</span>
          <strong>전자 기록 완료</strong>
          <small>{formatDate(document.approvedAt)}</small>
        </div>
      </div>
    </section>

    <section className="refund-audit-panel">
      <div><LockKeyhole aria-hidden="true" /><span><strong>변경 불가능한 감사 기록</strong><small>review_report/1.0.0 고정 스냅샷</small></span></div>
      <dl>
        <div><dt>보고서 ID</dt><dd><AuditValue>{document.reportId}</AuditValue></dd></div>
        <div><dt>처리 요청 번호</dt><dd><AuditValue>{document.intentId}</AuditValue></dd></div>
        <div><dt>사전 확인 결과 번호</dt><dd><AuditValue>{document.resultId}</AuditValue></dd></div>
        <div><dt>결과</dt><dd>{document.resultOutcome}</dd></div>
        <div><dt>실제 부작용</dt><dd className={document.sideEffectsPerformed ? "refund-danger-text" : "refund-safe-text"}>{document.sideEffectsPerformed ? "발생" : "없음"}</dd></div>
        <div><dt>보고서 무결성 값</dt><dd><AuditValue>{document.reportHash}</AuditValue></dd></div>
        <div><dt>결정 무결성 값</dt><dd><AuditValue>{document.decisionHash}</AuditValue></dd></div>
        <div><dt>검토 자료 무결성 값</dt><dd><AuditValue>{document.packetHash}</AuditValue></dd></div>
      </dl>
    </section>

    <footer className="refund-document-footer">
      <p>CSight 상담 처리 지원 화면에서 생성된 외부 처리 전 확인서입니다.</p>
      <strong>실제 카드 승인 취소, 계좌 환급, 상품 회수 또는 고객 통지는 수행되지 않았습니다.</strong>
    </footer>
  </article>;
}
