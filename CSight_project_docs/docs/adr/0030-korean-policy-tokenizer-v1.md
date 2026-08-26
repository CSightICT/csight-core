# ADR-0030: Korean Policy Tokenizer v1

- 상태: Accepted
- 일자: 2026-08-26

## Decision

`ko_policy_lexical:1.0.0`은 Unicode NFKC, Latin lowercase, 날짜·숫자·clause term 보존,
한글 character bigram, 최소 stopword를 고정한다.

## Consequences

동일 tokenizer version의 의미는 바꾸지 않는다. 변경은 새 profile/version과 dev 평가가 필요하다.
