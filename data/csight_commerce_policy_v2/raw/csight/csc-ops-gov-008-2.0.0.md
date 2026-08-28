---
tenant_id: csight
document_id: CSC-OPS-GOV-008
document_version: 2.0.0
title: CSight Commerce 사람 검토·자동화 통제 운영규정
policy_type: HIGH_RISK_EXCEPTION
authority_level: CSIGHT_COMMERCE_GOVERNANCE
product_categories: GENERAL
effective_from: 2026-08-28
effective_to:
status: ACTIVE
source_type: SYNTHETIC_REFERENCE
supersedes:
superseded_by:
---
# CSight Commerce 사람 검토·자동화 통제 운영규정

> CSight PoC 전용 완전 가상 사내 규정이다. 실제 기업 정책이나 법률 자문이 아니며 최종 처분은 사람 검토자가 결정한다.

## C1 [RULE]

모델 분석, 검색 인용과 typed rule 효과는 상담원에게 검토 후보, 증거 요구, 예외와 이관 신호만 제공한다. 승인, 거절, 환불, 교환, 재배송 또는 수리의 최종 결정으로 사용하지 않는다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,LEAKAGE,MISSING_COMPONENT,CONTAMINATION,WRONG_ITEM,FUNCTIONAL_FAILURE; actions=REVIEW

## C2 [RULE]

최종 Human Decision은 인증된 검토자가 검토 Packet과 적용 정책을 확인한 뒤에만 기록한다. 모델이나 worker는 고객에 대한 최종 업무 결정을 생성할 권한이 없다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,LEAKAGE,MISSING_COMPONENT,CONTAMINATION,WRONG_ITEM,FUNCTIONAL_FAILURE; actions=REVIEW,RESOLVE

## C3 [EVIDENCE_REQUIREMENT]

검토 화면은 Evidence, Rule, Citation, Grounding, 모델 qualification과 적용 정책 버전을 함께 제시해야 한다. 근거 hash가 불일치하면 조회 또는 Resolve를 fail-closed 처리한다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,LEAKAGE,MISSING_COMPONENT,CONTAMINATION,WRONG_ITEM,FUNCTIONAL_FAILURE; actions=REVIEW

## C4 [EXCEPTION]

한 Case에서 서로 다른 두 번째 Human Decision, tenant 불일치, 권한 없는 결정 또는 출처가 다른 결과가 발견되면 기존 결정을 자동 대체하지 않고 관리자 수동 후속 조치로 전환한다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,LEAKAGE,MISSING_COMPONENT,CONTAMINATION,WRONG_ITEM,FUNCTIONAL_FAILURE; actions=ESCALATE,REVIEW; parent=C1

## C5 [PROCEDURE]

외부 실행은 본 가상 정책 v2의 범위가 아니다. DRY-RUN은 부작용 없이 계약만 검증하며 LIVE 요청은 항상 차단한다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,LEAKAGE,MISSING_COMPONENT,CONTAMINATION,WRONG_ITEM,FUNCTIONAL_FAILURE; actions=SIMULATE,REVIEW

## C6 [ESCALATION]

Vision qualification이 PoC 또는 Mock 등급이거나 LLM 추출, 이미지, 정책 근거가 불일치하면 자동화를 금지하고 사람 검토로 이관한다.

Tags: categories=GENERAL; defects=BREAKAGE,PACKAGING_DAMAGE,LEAKAGE,MISSING_COMPONENT,CONTAMINATION,WRONG_ITEM,FUNCTIONAL_FAILURE; actions=ESCALATE,REVIEW
