import { ArrowLeft, ArrowRight, Info } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { Card, Notice, PageHeader, friendlyError } from "../components/Ui";
import { newOpaqueKey } from "../recovery/workflowCheckpoint";

const ACTIONS = ["UNSPECIFIED", "REFUND", "EXCHANGE", "RETURN", "REPAIR", "INFORMATION", "OTHER"] as const;

export function NewCasePage() {
  const navigate = useNavigate();
  const [action, setAction] = useState<(typeof ACTIONS)[number]>("UNSPECIFIED");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const data = new FormData(event.currentTarget);
    const external: Record<string, string | number> = {};
    if (action === "REFUND") {
      const amount = String(data.get("amount") ?? "");
      const currency = String(data.get("currency") ?? "");
      if (amount) external.amount = amount;
      if (currency) external.currency = currency;
    }
    if (["EXCHANGE", "REPAIR"].includes(action)) {
      const quantity = String(data.get("quantity") ?? "").trim();
      if (quantity) external.quantity = Number(quantity);
    }
    if (action === "EXCHANGE") {
      const shippingRef = String(data.get("shipping_address_ref") ?? "").trim();
      if (shippingRef) external.shipping_address_ref = shippingRef;
    }
    try {
      const created = await api.createCase({
        order_ref: String(data.get("order_ref") ?? "").trim(),
        product_ref: String(data.get("product_ref") ?? "").trim(),
        customer_message: String(data.get("customer_message") ?? "").trim(),
        requested_action: action,
        attributes: Object.keys(external).length ? { external_action_input: external } : {},
      }, newOpaqueKey());
      navigate(`/cases/${created.case_id}`);
    } catch (cause) {
      setError(friendlyError(cause));
    } finally {
      setSubmitting(false);
    }
  }

  const showsExternal = ["REFUND", "EXCHANGE", "REPAIR"].includes(action);
  return <div className="page page-narrow">
    <PageHeader eyebrow="New case" title="새 상담 케이스" description="고객이 제공한 내용만 입력합니다. 없는 값을 추정하거나 자동으로 채우지 않습니다."
      actions={<Link className="button button-ghost" to="/cases"><ArrowLeft size={18} />목록</Link>} />
    <form onSubmit={submit}>
      <Card title="기본 정보" description="주문과 상품을 식별하는 내부 참조값입니다.">
        <div className="form-grid">
          <label>주문 참조<input name="order_ref" required maxLength={200} placeholder="ORD-2026-00142" /></label>
          <label>상품 참조<input name="product_ref" required maxLength={200} placeholder="SKU-A100" /></label>
          <label className="full-field">고객 문의<textarea name="customer_message" required maxLength={20000} rows={6} placeholder="고객이 전달한 현상과 요청을 원문에 가깝게 입력하세요." /></label>
          <label>요청 유형<select name="requested_action" value={action} onChange={(event) => setAction(event.target.value as typeof action)}>{ACTIONS.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        </div>
      </Card>
      {showsExternal && <Card title="외부 조치 입력" description="5C에서는 이 화면에서 최초 입력만 받으며, 누락 시 보류됩니다." className="spaced-card">
        <Notice title="안전한 입력 원칙"><span>금액·통화·수량·배송지 참조는 문의 내용이나 AI 설명에서 추정하지 않습니다. 비워두면 <strong>ACTION_NEEDS_INPUT</strong>으로 표시되고 모의 실행을 만들지 않습니다.</span></Notice>
        <div className="form-grid action-fields">
          {action === "REFUND" && <>
            <label>환불 금액<input name="amount" type="text" inputMode="decimal" maxLength={20} pattern="[0-9]{1,15}(\.[0-9]{1,4})?" placeholder="예: 48000.00" /></label>
            <label>통화 코드<input name="currency" maxLength={3} pattern="[A-Z]{3}" placeholder="KRW" /></label>
          </>}
          {["EXCHANGE", "REPAIR"].includes(action) && <label>수량<input name="quantity" type="number" min="1" max="1000" step="1" inputMode="numeric" placeholder="1" /></label>}
          {action === "EXCHANGE" && <label>배송지 참조<input name="shipping_address_ref" maxLength={200} placeholder="ADDR-…" /></label>}
        </div>
        <p className="field-help"><Info size={15} /> 주문 참조와 상품 참조는 위 기본 정보 값을 그대로 사용합니다. 중첩 객체나 추가 필드는 전송하지 않습니다.</p>
      </Card>}
      {error && <div className="inline-alert inline-alert-danger form-error" role="alert">{error}</div>}
      <div className="form-actions"><Link className="button button-secondary" to="/cases">취소</Link><button className="button button-primary button-large" disabled={submitting} type="submit">{submitting ? "등록 중…" : "케이스 등록"}<ArrowRight size={18} /></button></div>
    </form>
  </div>;
}
