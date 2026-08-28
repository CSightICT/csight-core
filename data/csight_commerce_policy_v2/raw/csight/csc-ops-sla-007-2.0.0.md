---
tenant_id: csight
document_id: CSC-OPS-SLA-007
document_version: 2.0.0
title: CSight Commerce 기간·예외·이관 운영규정
policy_type: HIGH_RISK_EXCEPTION
authority_level: CSIGHT_COMMERCE_OPERATIONS_CONTROL
product_categories: GENERAL
effective_from: 2026-08-28
effective_to:
status: ACTIVE
source_type: SYNTHETIC_REFERENCE
supersedes:
superseded_by:
---
# CSight Commerce 기간·예외·이관 운영규정

> CSight PoC 전용 완전 가상 사내 규정이다. 실제 기업 정책이나 법률 자문이 아니며 최종 처분은 사람 검토자가 결정한다.

## C1 [RULE]

수령 후 7일 이내의 배송손상과 초기불량 주장은 우선 검토 대상으로 표시한다. 우선 검토는 처리 방향이나 고객 책임을 확정하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,FUNCTIONAL_FAILURE,WRONG_ITEM,MISSING_COMPONENT; actions=REVIEW

## C2 [RULE]

수령 후 14일 이내의 반품, 교환, 환불 요청은 표준 기간 검토 대상으로 표시한다. 구매일 또는 수령일이 불명확하면 기간 조건을 만족한 것으로 가정하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,FUNCTIONAL_FAILURE,WRONG_ITEM,MISSING_COMPONENT; actions=RETURN,EXCHANGE,REFUND,REVIEW

## C3 [EVIDENCE_REQUIREMENT]

기간 판정에는 고객 진술만으로 생성한 날짜가 아니라 Case에 명시적으로 기록된 구매 또는 수령 기준일을 사용한다. 기준일이 없으면 추가 정보 필요로 처리한다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,FUNCTIONAL_FAILURE,WRONG_ITEM,MISSING_COMPONENT; actions=REQUEST_EVIDENCE,REVIEW

## C4 [EXCEPTION]

14일을 초과하거나 30일을 초과한 Case, 반복 처리 Case, 안전 Case는 표준 규칙의 자동 연장 또는 자동 거절 대상으로 보지 않는다. 정책 예외와 관리자 검토를 적용한다.

Tags: categories=GENERAL; defects=BREAKAGE,FUNCTIONAL_FAILURE,LEAKAGE,CONTAMINATION; actions=ESCALATE,REVIEW; parent=C2

## C5 [PROCEDURE]

예외 검토에는 경과 일수, 사유, 확보 증거, 이전 처리 이력과 상담원 판단 근거를 기록한다. 결론이 없을 때 Case를 조기에 종료하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,FUNCTIONAL_FAILURE,LEAKAGE,CONTAMINATION; actions=REVIEW

## C6 [ESCALATION]

기간 기준과 안전 기준이 충돌하거나 서로 다른 정책 버전이 적용될 가능성이 있으면 최신 ACTIVE 규정과 사건 기준일을 관리자와 확인한다.

Tags: categories=GENERAL; defects=BREAKAGE,FUNCTIONAL_FAILURE,LEAKAGE,CONTAMINATION; actions=ESCALATE,REVIEW
