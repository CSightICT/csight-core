---
tenant_id: csight
document_id: CSC-OPS-REP-003
document_version: 2.0.0
title: CSight Commerce 초기불량·수리 검토 운영규정
policy_type: FUNCTIONAL_FAILURE
authority_level: CSIGHT_COMMERCE_SERVICE
product_categories: GENERAL
effective_from: 2026-08-28
effective_to:
status: ACTIVE
source_type: SYNTHETIC_REFERENCE
supersedes:
superseded_by:
---
# CSight Commerce 초기불량·수리 검토 운영규정

> CSight PoC 전용 완전 가상 사내 규정이다. 실제 기업 정책이나 법률 자문이 아니며 최종 처분은 사람 검토자가 결정한다.

## C1 [RULE]

수령 후 7일 이내 발생한 전원, 작동, 체결 또는 펌프 기능 이상 주장은 초기불량 검토 대상으로 표시한다. 시스템은 증상 분류를 근거로 수리나 교환을 자동 확정하지 않는다.

Tags: categories=GENERAL; defects=FUNCTIONAL_FAILURE; actions=REPAIR,EXCHANGE,REVIEW

## C2 [EVIDENCE_REQUIREMENT]

수리 검토에는 상품 식별 정보, 증상 설명, 안전하게 촬영 가능한 작동 상태 이미지 또는 영상 참조가 필요하다. 위험 가능성이 있으면 재현을 요구하지 않고 현재 상태만 기록한다.

Tags: categories=GENERAL; defects=FUNCTIONAL_FAILURE; actions=REPAIR,REQUEST_EVIDENCE,REVIEW

## C3 [RULE]

개봉 또는 짧은 시험 사용은 초기불량 주장을 자동 배제하는 사유로 사용하지 않는다. 사용 중 손상 여부, 발생 시점, 상품 특성을 상담원이 검토해 수리·교환 후보를 분리한다.

Tags: categories=GENERAL; defects=FUNCTIONAL_FAILURE,BREAKAGE; actions=REPAIR,EXCHANGE,REVIEW

## C4 [EXCEPTION]

동일 증상이 수리 후 반복되었거나 이전 처리 이력을 확인할 수 없으면 표준 수리 검토를 중단하고 정책 예외 및 관리자 검토로 이관한다.

Tags: categories=GENERAL; defects=FUNCTIONAL_FAILURE; actions=REPAIR,ESCALATE; parent=C1

## C5 [PROCEDURE]

부품, 작업 범위, 비용, 기간은 확인된 서비스 입력으로만 기록한다. 모델 설명이나 고객의 추정 원인에서 부품 번호와 비용을 생성하지 않는다.

Tags: categories=GENERAL; defects=FUNCTIONAL_FAILURE,MISSING_COMPONENT; actions=REPAIR,REQUEST_EVIDENCE

## C6 [ESCALATION]

발열, 연기, 전기적 위험, 누액 또는 신체 위해 가능성이 있는 기능 이상은 일반 수리 안내보다 안전 검토를 우선하고 관리자에게 이관한다.

Tags: categories=GENERAL; defects=FUNCTIONAL_FAILURE,LEAKAGE; actions=ISOLATE,ESCALATE,REVIEW
