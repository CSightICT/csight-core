"""Versioned reciprocal-rank fusion without raw-score mixing."""

from collections.abc import Sequence

from app.platform.policy_retrieval import (
    HybridFusionProfile,
    PolicySearchHit,
)


class ReciprocalRankFusionRetriever:
    def fuse(
        self,
        *,
        lexical_hits: Sequence[PolicySearchHit],
        dense_hits: Sequence[PolicySearchHit],
        profile: HybridFusionProfile,
        top_k: int,
    ) -> tuple[PolicySearchHit, ...]:
        by_key: dict[tuple[str, str, str, str], PolicySearchHit] = {}
        scores: dict[tuple[str, str, str, str], float] = {}
        for hit in lexical_hits:
            key = hit.clause.dedupe_key
            by_key[key] = hit
            rank = hit.lexical_rank
            if rank is not None:
                scores[key] = scores.get(key, 0.0) + profile.lexical_weight / (profile.rrf_k + rank)
        for hit in dense_hits:
            key = hit.clause.dedupe_key
            existing = by_key.get(key)
            by_key[key] = (
                hit
                if existing is None
                else existing.model_copy(
                    update={"dense_rank": hit.dense_rank, "dense_score": hit.dense_score}
                )
            )
            rank = hit.dense_rank
            if rank is not None:
                scores[key] = scores.get(key, 0.0) + profile.dense_weight / (profile.rrf_k + rank)
        ordered = sorted(scores, key=lambda key: (-scores[key], key))
        return tuple(
            by_key[key].model_copy(update={"fusion_rank": rank, "fusion_score": scores[key]})
            for rank, key in enumerate(ordered[:top_k], start=1)
        )


__all__ = ["ReciprocalRankFusionRetriever"]
