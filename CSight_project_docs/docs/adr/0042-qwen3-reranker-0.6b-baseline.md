# ADR-0042: Qwen3-Reranker-0.6B baseline

- Status: Accepted
- Date: 2026-08-26

## Decision

Use `Qwen/Qwen3-Reranker-0.6B` revision
`e61197ed45024b0ed8a2d74b80b4d909f1255473` in a separate host-native MPS service. Follow the
official causal-LM yes/no scoring example with left padding and fixed prefix/suffix.

## Consequences

The model loads independently from Core and embedding runtimes. MPS is qualified with concurrency
one; CPU fallback was unnecessary.
