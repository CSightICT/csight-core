# ADR-0021: Policy RAG는 최종 업무 결정을 만들지 않는다

- 상태: Accepted
- 일자: 2026-08-26

## Decision

Query Builder는 tenant를 생성·변경하지 않고 Application이 filter를 주입한다. Grounded
Explanation은 제공된 clause ID만 인용하고 applicable evidence와 unresolved condition만
반환한다. 승인·거절·사기·책임·final decision field는 금지한다.

## Consequences

검색과 설명은 근거 보조이며 versioned policy evaluator와 Human Review가 최종 결정을 소유한다.
