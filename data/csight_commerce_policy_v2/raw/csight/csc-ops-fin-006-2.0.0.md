---
tenant_id: csight
document_id: CSC-OPS-FIN-006
document_version: 2.0.0
title: CSight Commerce 금액·통화·비용 통제 운영규정
policy_type: HIGH_RISK_EXCEPTION
authority_level: CSIGHT_COMMERCE_FINANCE_CONTROL
product_categories: GENERAL
effective_from: 2026-08-28
effective_to:
status: ACTIVE
source_type: SYNTHETIC_REFERENCE
supersedes:
superseded_by:
---
# CSight Commerce 금액·통화·비용 통제 운영규정

> CSight PoC 전용 완전 가상 사내 규정이다. 실제 기업 정책이나 법률 자문이 아니며 최종 처분은 사람 검토자가 결정한다.

## C1 [RULE]

환불 또는 유상 수리 검토에 금액이 필요한 경우 금액과 통화는 명시적 입력으로 함께 기록한다. 주문 총액이나 자연어 rationale를 실제 실행 금액으로 자동 전환하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,FUNCTIONAL_FAILURE,LEAKAGE; actions=REFUND,REPAIR,REVIEW

## C2 [RULE]

Case 주문금액이 100000원을 초과하는 경우에는 고액 검토 표식을 적용하고 관리자 검토를 요구한다. 이 임계값은 가상 데모 운영 기준이며 보상 승인 기준이 아니다.

Tags: categories=GENERAL; defects=BREAKAGE,FUNCTIONAL_FAILURE,LEAKAGE,WRONG_ITEM; actions=ESCALATE,REVIEW

## C3 [EVIDENCE_REQUIREMENT]

부분 환불, 수량 기반 환불, 배송비 또는 수리비가 언급되면 계산 근거와 적용 통화를 별도 입력으로 확보한다. 누락 시 금액을 0 또는 주문 총액으로 기본 설정하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,FUNCTIONAL_FAILURE,MISSING_COMPONENT; actions=REFUND,REPAIR,REQUEST_EVIDENCE

## C4 [EXCEPTION]

금액과 통화가 충돌하거나 복수 상품 금액이 합산된 Case는 고액 여부와 관계없이 정책 예외로 분류하고 관리자에게 이관한다.

Tags: categories=GENERAL; defects=BREAKAGE,FUNCTIONAL_FAILURE,MISSING_COMPONENT,WRONG_ITEM; actions=ESCALATE,REVIEW; parent=C1

## C5 [PROCEDURE]

DRY-RUN 결과는 입력 계약 검증을 보여주는 시뮬레이션이며 결제, 환불, 송금 또는 외부 시스템 변경을 수행하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,FUNCTIONAL_FAILURE,LEAKAGE,MISSING_COMPONENT,WRONG_ITEM; actions=REFUND,REPAIR,SIMULATE

## C6 [ESCALATION]

금액 승인권자, 통화, 수량 또는 계산 근거가 없으면 상담원이 추가 입력을 요청한다. 사람의 명시적 결정 전에는 외부 Action Intent를 최종 실행으로 취급하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,FUNCTIONAL_FAILURE,LEAKAGE,MISSING_COMPONENT,WRONG_ITEM; actions=ESCALATE,REQUEST_EVIDENCE

## C7 [RULE]

무하자 단순변심 반품의 반품비 부담 여부는 상품 상태, 반품 사유, 배송 단계와 별도 비용 기준을 확인하는 검토 후보로만 표시한다. 고객 또는 판매자 부담을 자동 확정하거나 확인되지 않은 비용 금액을 생성하지 않는다.

Tags: categories=GENERAL; defects=; actions=RETURN,CHANGE_OF_MIND,COST_REVIEW

## C8 [PROCEDURE]

취소·반품 환불 문의에는 현재 취소 가능 상태, 입고·검수 여부, 확정된 환불 금액과 통화, 후속 처리 단계를 구분해 안내한다. 확인되지 않은 환불 일정이나 카드·계좌 반영 시점을 약속하지 않는다.

Tags: categories=GENERAL; defects=; actions=REFUND,INFORMATION,REVIEW
