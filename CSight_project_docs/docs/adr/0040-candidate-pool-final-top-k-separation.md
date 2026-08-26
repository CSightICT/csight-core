# ADR-0040: Separate candidate pool K from final top-K

- Status: Accepted
- Date: 2026-08-26

## Decision

The ACTIVE execution profile fixes `candidate_k=20` and `final_k=10`. Clients may request fewer final
hits but cannot select candidate K, model or profile.

## Consequences

Candidate recall and ranking quality remain independently measurable. Expanding K does not silently
change the existing LEXICAL, DENSE or HYBRID API modes.
