# ADR-0032: Embedding Profile and Instruction Versioning

- 상태: Accepted
- 일자: 2026-08-26

## Decision

artifact/revision/dimension/pooling/normalization, query instruction, passage template, token limit와 각 hash를
`qwen3_embedding_0.6b:1.0.0`에 고정한다.

## Consequences

instruction이나 serialization 변경은 기존 embedding을 덮어쓰지 않고 새 profile로 rebuild해야 한다.
