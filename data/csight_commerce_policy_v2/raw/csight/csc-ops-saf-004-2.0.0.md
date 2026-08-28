---
tenant_id: csight
document_id: CSC-OPS-SAF-004
document_version: 2.0.0
title: CSight Commerce 누액·오염·안전사건 운영규정
policy_type: LEAKAGE_CONTAMINATION
authority_level: CSIGHT_COMMERCE_SAFETY
product_categories: GENERAL
effective_from: 2026-08-28
effective_to:
status: ACTIVE
source_type: SYNTHETIC_REFERENCE
supersedes:
superseded_by:
---
# CSight Commerce 누액·오염·안전사건 운영규정

> CSight PoC 전용 완전 가상 사내 규정이다. 실제 기업 정책이나 법률 자문이 아니며 최종 처분은 사람 검토자가 결정한다.

## C1 [RULE]

누액, 내용물 유출, 이물 혼입 또는 오염 주장은 안전 우선 Case로 표시한다. 고객에게 사용 중지와 접촉 최소화를 안내할 수 있으나 책임, 환불 또는 폐기 결론은 자동화하지 않는다.

Tags: categories=GENERAL; defects=LEAKAGE,CONTAMINATION; actions=ISOLATE,REVIEW

## C2 [EVIDENCE_REQUIREMENT]

안전사건 증거는 위험을 늘리지 않는 범위에서 밀봉 상태, 외부 포장, 오염 범위와 상품 식별 정보를 확보한다. 냄새 확인, 재작동, 용기 개봉 또는 직접 접촉을 요구하지 않는다.

Tags: categories=GENERAL; defects=LEAKAGE,CONTAMINATION; actions=REQUEST_EVIDENCE,ISOLATE

## C3 [RULE]

누액 또는 오염 Case의 교환, 환불, 재배송, 수리 요청은 모두 사람 검토 대상으로 유지한다. 모델과 typed rule의 결과는 우선순위와 필요한 자료를 제안할 뿐 최종 처분이 아니다.

Tags: categories=GENERAL; defects=LEAKAGE,CONTAMINATION; actions=EXCHANGE,REFUND,RESHIPMENT,REPAIR,REVIEW

## C4 [EXCEPTION]

피부 접촉, 호흡기 자극, 발열, 팽창, 다수 상품 오염 또는 주변 확산이 언급되면 일반 안전 분류보다 높은 관리자 검토와 자동화 금지를 적용한다.

Tags: categories=GENERAL; defects=LEAKAGE,CONTAMINATION; actions=ESCALATE,ISOLATE; parent=C1

## C5 [PROCEDURE]

안전사건에서는 운송, 회수, 폐기 방법을 추론하지 않는다. 승인된 담당자가 제공한 지침이 없으면 Case를 사람 검토 상태로 유지한다.

Tags: categories=GENERAL; defects=LEAKAGE,CONTAMINATION; actions=REVIEW,ESCALATE

## C6 [ESCALATION]

안전 증거가 불완전하거나 고객 설명과 이미지가 불일치해도 자동 기각하지 않는다. 안전 관리자에게 이관하고 추가 자료가 위해를 높이는지 먼저 판단한다.

Tags: categories=GENERAL; defects=LEAKAGE,CONTAMINATION; actions=ESCALATE,REQUEST_EVIDENCE
