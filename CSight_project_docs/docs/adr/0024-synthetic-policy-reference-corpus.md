# ADR-0024: 합성 Policy Reference Corpus

- 상태: Accepted
- 일자: 2026-08-26

## Decision

실제 기업 문서가 없으므로 모든 문서와 manifest를 `SYNTHETIC_REFERENCE`로 표시하고 실제
브랜드·법적 효력을 주장하지 않는다. Raw Markdown은 build가 수정하지 않으며 normalized,
clauses, manifests와 reports만 생성한다.

## Consequences

PoC 검색·평가 계약은 검증할 수 있지만 실제 기업 정책 정확성이나 법률 적합성을 의미하지 않는다.
