---
tenant_id: csight
document_id: CSC-OPS-EVD-005
document_version: 2.0.0
title: CSight Commerce 증거·식별·추가자료 운영규정
policy_type: EVIDENCE_REQUIREMENT
authority_level: CSIGHT_COMMERCE_CONTROL
product_categories: GENERAL
effective_from: 2026-08-28
effective_to:
status: ACTIVE
source_type: SYNTHETIC_REFERENCE
supersedes:
superseded_by:
---
# CSight Commerce 증거·식별·추가자료 운영규정

> CSight PoC 전용 완전 가상 사내 규정이다. 실제 기업 정책이나 법률 자문이 아니며 최종 처분은 사람 검토자가 결정한다.

## C1 [RULE]

정책 검토는 Case의 주문 참조와 상품 참조를 기준 식별자로 사용한다. 두 값 중 하나라도 없으면 결론을 보완하지 않고 추가 정보 필요 상태로 표시한다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,LEAKAGE,MISSING_COMPONENT,CONTAMINATION,WRONG_ITEM,FUNCTIONAL_FAILURE; actions=REQUEST_EVIDENCE,REVIEW

## C2 [EVIDENCE_REQUIREMENT]

이미지 기반 결함 주장에는 상품 전체와 주장 부위를 확인할 수 있는 최소 한 장의 증거가 필요하다. 식별 불가, 과도한 흐림, 다른 상품의 이미지 가능성이 있으면 자료 재요청 사유를 명시한다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,LEAKAGE,MISSING_COMPONENT,CONTAMINATION,WRONG_ITEM,FUNCTIONAL_FAILURE; actions=REQUEST_EVIDENCE,REVIEW

## C3 [RULE]

고객이 제출하지 않은 금액, 통화, 수량, 배송지, 구매일 또는 상품 옵션을 모델 출력, 주문금액, rationale이나 관행에서 추론하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,LEAKAGE,MISSING_COMPONENT,CONTAMINATION,WRONG_ITEM,FUNCTIONAL_FAILURE; actions=REQUEST_EVIDENCE,REVIEW

## C4 [EXCEPTION]

안전 위험으로 촬영이나 재현이 부적절한 경우에는 이미지 수 기준을 기계적으로 적용하지 않는다. 상담원은 안전 우선 사유를 기록하고 가능한 대체 증거를 관리자와 검토한다.

Tags: categories=GENERAL; defects=LEAKAGE,CONTAMINATION,FUNCTIONAL_FAILURE; actions=ESCALATE,REQUEST_EVIDENCE; parent=C1

## C5 [PROCEDURE]

증거의 원본 hash, 업로드 주체, Case 연결과 생성 시각을 보존하고 조회 시 tenant와 Case 권한을 확인한다. 출처가 불명확하거나 무결성이 깨진 증거는 정책 근거로 사용하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,LEAKAGE,MISSING_COMPONENT,CONTAMINATION,WRONG_ITEM,FUNCTIONAL_FAILURE; actions=REVIEW

## C6 [ESCALATION]

복수 주장, 상충 증거, 상품 식별 불일치 또는 동일 증거의 재사용 의심은 자동 처리 금지와 사람 검토 대상으로 이관한다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,LEAKAGE,MISSING_COMPONENT,CONTAMINATION,WRONG_ITEM,FUNCTIONAL_FAILURE; actions=ESCALATE,REVIEW
