---
tenant_id: csight
document_id: CSC-OPS-RET-001
document_version: 2.0.0
title: CSight Commerce 반품·교환·환불 접수 운영규정
policy_type: RETURN_EXCHANGE
authority_level: CSIGHT_COMMERCE_OPERATIONS
product_categories: GENERAL
effective_from: 2026-08-28
effective_to:
status: ACTIVE
source_type: SYNTHETIC_REFERENCE
supersedes:
superseded_by:
---
# CSight Commerce 반품·교환·환불 접수 운영규정

> CSight PoC 전용 완전 가상 사내 규정이다. 실제 기업 정책이나 법률 자문이 아니며 최종 처분은 사람 검토자가 결정한다.

## C1 [RULE]

수령일로부터 14일 이내에 접수된 반품 요청은 표준 검토 대상으로 표시한다. 기간 충족은 승인 의미가 아니며 주문, 상품, 상태, 고객 요청을 상담원이 함께 확인해야 한다.

Tags: categories=GENERAL; defects=FUNCTIONAL_FAILURE,PACKAGING_DAMAGE; actions=RETURN,REVIEW

## C2 [RULE]

교환 또는 환불 요청은 고객이 명시한 요청 유형을 그대로 기록하고, 결함 사실과 처리 가능성을 별도로 검토한다. 시스템은 교환과 환불 중 하나를 자동 선택하거나 최종 결론으로 제시하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,FUNCTIONAL_FAILURE,WRONG_ITEM; actions=EXCHANGE,REFUND,REVIEW

## C3 [EVIDENCE_REQUIREMENT]

개봉 후 발견한 초기불량은 개봉 자체만으로 제외하지 않는다. 상품 전체, 결함 부위, 주문·상품 참조와 발견 시점 설명을 확보하고 사용 흔적과 초기불량 주장을 구분해 사람 검토에 제공한다.

Tags: categories=GENERAL; defects=FUNCTIONAL_FAILURE,BREAKAGE; actions=RETURN,EXCHANGE,REFUND,REVIEW

## C4 [EXCEPTION]

14일을 초과했거나 구매일을 확정할 수 없는 요청은 표준 기간 규칙을 적용한 것으로 간주하지 않는다. 30일 이내의 초기불량 주장도 예외 표식과 관리자 검토를 거쳐야 하며 자동 승인 또는 자동 거절하지 않는다.

Tags: categories=GENERAL; defects=FUNCTIONAL_FAILURE,BREAKAGE; actions=RETURN,EXCHANGE,REFUND,ESCALATE; parent=C1

## C5 [PROCEDURE]

단순 사용법, 구성품 확인, 보증 범위 문의처럼 고객이 정보만 요청한 경우에는 정보 안내 검토로 분류한다. 상담원은 확인된 정책 조항을 인용하고 결함 처분이나 외부 실행을 생성하지 않는다.

Tags: categories=GENERAL; defects=; actions=INFORMATION,REVIEW

## C6 [ESCALATION]

동일 Case에 서로 다른 처리 요청이 공존하거나 고객 요청과 증거가 충돌하면 상담원이 우선순위를 확인한다. 자동화는 기존 결정을 대체하지 않으며 필요한 경우 관리자에게 이관한다.

Tags: categories=GENERAL; defects=BREAKAGE,FUNCTIONAL_FAILURE,WRONG_ITEM; actions=RETURN,EXCHANGE,REFUND,REPAIR,ESCALATE

## C7 [RULE]

무하자 단순변심 반품은 수령 후 14일 이내라는 기간, 미사용 여부, 구성품 완전성, 상품·내부 포장 상태를 함께 확인하는 검토 후보로 표시한다. 개봉 또는 포장 훼손 여부만으로 즉시 승인·거절하지 않고 상품 특성과 재판매 가능성은 상담원이 판단한다.

Tags: categories=GENERAL; defects=; actions=RETURN,CHANGE_OF_MIND,REVIEW

## C8 [PROCEDURE]

환불 안내 시점은 취소 가능 상태, 반품 입고와 검수 상태, 금액·통화 확인 결과에 따라 상담원이 설명한다. 시스템은 고정 환불 완료일이나 지급 보장을 생성하지 않고 확인된 단계와 추가 확인 항목만 제시한다.

Tags: categories=GENERAL; defects=; actions=REFUND,INFORMATION,REVIEW
