# ADR-0037: Locked Dev/Test Retrieval Evaluation

- 상태: Accepted
- 일자: 2026-08-26

## Decision

Retrieval dev 80건에서 BM25와 RRF를 선택하고 profile/hash를 freeze한 뒤 test 40건을 한 번만
평가한다. Dense artifact와 instruction도 freeze metadata에 포함한다.

## Consequences

Test 결과에 맞춘 재튜닝과 재평가를 금지한다. 현재 profile은 `test_evaluated=true`이며 test 명령을
다시 실행하지 않는다.
