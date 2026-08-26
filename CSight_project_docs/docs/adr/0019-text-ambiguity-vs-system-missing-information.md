# ADR-0019: Text Ambiguity와 System Missing Information 분리

- 상태: Accepted
- 일자: 2026-08-26

## Context

기존 missing field는 텍스트 모호성과 DB/Evidence 누락을 함께 LLM에 요구했다.

## Decision

LLM은 고객 문장만으로 보이는 `text_ambiguities`만 생성한다. 주문·상품 참조, AVAILABLE 이미지,
고객 요청 누락은 Backend completeness rule `1.0.0`이 Case/Evidence/v2 Result로 계산한다.

## Consequences

같은 DB 상태에 같은 결정적 결과를 얻고 LLM 평가 label의 책임 경계가 명확해진다.
