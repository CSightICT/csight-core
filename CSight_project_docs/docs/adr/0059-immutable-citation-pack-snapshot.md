# ADR-0059: Immutable citation pack snapshot

- Status: Accepted
- Date: 2026-08-27

## Decision

Create one immutable citation pack from each successful policy retrieval run. Snapshot rank, clause
and document identity/version, title, section path, type, clause text, effective interval, source
type/hash, retrieval mode, query strategy, matched query IDs, and retrieval profile hash.

## Consequences

Later policy changes cannot alter the evidence observed by an explanation run. Packs are tenant- and
retrieval-run scoped, content hashed, append-only, and never accept client-supplied clause IDs.
