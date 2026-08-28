# Refund Processing Confirmation

- Status: Implemented for the synthetic CSight Commerce demo
- Date: 2026-08-28
- Contract source: immutable `review_report/1.0.0` snapshot
- External execution: disabled; `DRY_RUN` only

## Purpose

The consultant console renders an approved refund as a familiar operations document named
`환불 처리 확인서`. It is a processing confirmation for an internal simulation, not a payment
receipt, card-cancellation receipt, tax invoice, or proof that money reached a customer.

The layout is informed by common fields in official commerce and payment-provider guidance. It does
not copy the visual identity, wording, or proprietary form of a real company.

## Reference-informed field set

| Official reference | Operational concepts used by CSight |
|---|---|
| [Shopify Help: Refunding orders](https://help.shopify.com/en/manual/fulfillment/managing-orders/refunding-orders) | full/partial amount, quantity, shipping adjustment, refund reason, refund method, customer notification, financial summary and timeline |
| [Stripe Docs: Refund and cancel payments](https://docs.stripe.com/refunds) | refund to the original payment method, pending/succeeded/failed lifecycle, failure reason, and provider-side reference |
| [Korean E-Commerce Consumer Protection Act, Article 18](https://www.law.go.kr/%EB%B2%95%EB%A0%B9/%EC%A0%84%EC%9E%90%EC%83%81%EA%B1%B0%EB%9E%98%EB%93%B1%EC%97%90%EC%84%9C%EC%9D%98%EC%86%8C%EB%B9%84%EC%9E%90%EB%B3%B4%ED%98%B8%EC%97%90%EA%B4%80%ED%95%9C%EB%B2%95%EB%A5%A0/%EC%A0%9C18%EC%A1%B0) | refund-request timing and whether payment-provider cancellation was requested and communicated |

These references explain why the document contains the following sections:

1. document number and generated time;
2. synthetic customer ID/name, masked phone, recipient, explicitly fictional delivery address;
3. order, product, quantity, paid amount, explicit refund amount, currency, and masked payment method;
4. original-payment-method route, payment-provider cancellation request, customer notification,
   return authorization, recovery/tracking, and expected date;
5. human decision, policy version and effective date, reviewer, and event timeline; and
6. immutable report/packet/decision/intent/result identifiers and hashes.

The demo does not calculate a statutory deadline or assert legal compliance. A production rollout
must bind the applicable jurisdiction, policy version, payment method, return condition, and actual
provider timestamps before showing a due date.

## Fail-closed rendering rules

- Refund amount and currency come only from the immutable Action Intent copied into the report.
  The synthetic paid amount is displayed separately for reconciliation and is never used as an
  inference source. Quantity, masked payment context, and masked tracking values also come only
  from the immutable report snapshot.
- Customer, contact, payment, tracking, and address fields are included only when a validated
  `synthetic_commerce_context/1.0.0` snapshot is present. Direct phone, card/account, and tracking
  values are never included.
- Missing required action inputs render as `환불 정보 보완 필요`; the document says that no
  Action Intent, Simulation Attempt, or Result was created where the database snapshot confirms it.
- `ACTION_DRY_RUN_VALIDATED` renders as `환불 요청 검증 완료`, never `환불 완료`.
- `side_effects_performed=false` renders as `실제 환불 상태: 미실행` and `실제 부작용: 없음`.
- Payment cancellation, customer notification, RMA, and tracking fields remain `미요청`, `미발송`,
  or `외부 시스템 미연동` until an authorized external adapter records real references.
- The authenticated Human Decision remains the final business decision. Model and policy outputs
  stay advisory and are not represented as the approver.

## Implementation

- `web/src/report/refundDocument.ts` maps the immutable snapshot to display-only document fields.
- `web/src/report/RefundConfirmation.tsx` renders the screen and printable A4-oriented document.
- Non-refund terminal decisions continue to use the generic immutable final-review report.
- ADR-0098 defines the synthetic-data and no-parameter-inference boundary.
