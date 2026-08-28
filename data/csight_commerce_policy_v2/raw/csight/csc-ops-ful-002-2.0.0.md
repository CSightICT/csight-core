---
tenant_id: csight
document_id: CSC-OPS-FUL-002
document_version: 2.0.0
title: CSight Commerce 배송손상·오배송·재배송 운영규정
policy_type: SHIPPING_DAMAGE
authority_level: CSIGHT_COMMERCE_FULFILLMENT
product_categories: GENERAL
effective_from: 2026-08-28
effective_to:
status: ACTIVE
source_type: SYNTHETIC_REFERENCE
supersedes:
superseded_by:
---
# CSight Commerce 배송손상·오배송·재배송 운영규정

> CSight PoC 전용 완전 가상 사내 규정이다. 실제 기업 정책이나 법률 자문이 아니며 최종 처분은 사람 검토자가 결정한다.

## C1 [RULE]

수령 후 7일 이내에 신고된 파손, 포장 손상, 오배송 또는 구성품 누락은 배송 품질 검토 대상으로 표시한다. 신고 기간은 검토 순서를 정하는 기준이며 책임이나 보상 결론을 확정하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,WRONG_ITEM,MISSING_COMPONENT; actions=RESHIPMENT,EXCHANGE,REVIEW

## C2 [EVIDENCE_REQUIREMENT]

배송손상 검토에는 외부 포장, 송장 식별 영역, 상품 전체, 손상 부위를 식별할 수 있는 사진을 우선 확보한다. 안전상 위험한 경우에는 포장을 추가로 열도록 요구하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE; actions=RESHIPMENT,EXCHANGE,REVIEW

## C3 [RULE]

재배송 검토는 주문 참조, 상품 참조, 누락 또는 오배송 내용이 명시된 경우에만 진행 상태를 표시한다. 수량이나 배송지 참조가 필요한 실행 단계에서는 고객이 명시적으로 제출한 값만 사용한다.

Tags: categories=GENERAL; defects=WRONG_ITEM,MISSING_COMPONENT,BREAKAGE; actions=RESHIPMENT,REVIEW

## C4 [EXCEPTION]

누액, 날카로운 파편, 오염 확산 또는 발열 등 안전 신호가 동반된 배송손상은 일반 재배송 검토보다 안전 격리와 사람 검토를 우선한다.

Tags: categories=GENERAL; defects=BREAKAGE,LEAKAGE,CONTAMINATION; actions=ISOLATE,ESCALATE,REVIEW; parent=C1

## C5 [PROCEDURE]

재배송 수량, 배송지, 상품 옵션은 문의 문장이나 기존 주문금액에서 추론하거나 기본값으로 채우지 않는다. 필수 입력이 없으면 추가 정보 필요 상태로 남기고 실행 시도 결과를 만들지 않는다.

Tags: categories=GENERAL; defects=WRONG_ITEM,MISSING_COMPONENT; actions=RESHIPMENT,REQUEST_EVIDENCE

## C6 [ESCALATION]

반복 배송손상, 다수 상품 피해, 증거 간 상품 식별 불일치 또는 동일 주문의 상충 요청은 관리자 검토 대상으로 이관한다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,WRONG_ITEM,MISSING_COMPONENT; actions=ESCALATE,REVIEW
