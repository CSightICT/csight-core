"""Deterministic exact BM25 over already metadata-filtered policy clauses."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

from app.platform.policy_retrieval import (
    LexicalProfile,
    PolicyClauseRecord,
    PolicySearchHit,
    PolicySearchQuery,
)

_TOKEN_PATTERN = re.compile(
    r"[A-Za-z]+(?:[-_.:/][A-Za-z0-9]+)*|\d+(?:[-./:]\d+)*|[가-힣]+",
    re.UNICODE,
)
_MINIMAL_STOPWORDS = frozenset({"및", "또는", "의", "은", "는", "이", "가", "을", "를"})


class KoreanPolicyTokenizerV1:
    """NFKC/lower tokenizer with preserved terms and Hangul character bigrams."""

    def tokenize(self, value: str) -> tuple[str, ...]:
        normalized = unicodedata.normalize("NFKC", value).lower()
        tokens: list[str] = []
        for token in _TOKEN_PATTERN.findall(normalized):
            if token not in _MINIMAL_STOPWORDS:
                tokens.append(token)
            if token and all("가" <= character <= "힣" for character in token):
                tokens.extend(f"ko2:{token[index : index + 2]}" for index in range(len(token) - 1))
        return tuple(tokens)


class ExactBM25Retriever:
    """Compute Robertson BM25 directly; score ties use the immutable clause key."""

    def __init__(self, tokenizer: KoreanPolicyTokenizerV1 | None = None) -> None:
        self._tokenizer = tokenizer or KoreanPolicyTokenizerV1()

    def retrieve(
        self,
        *,
        query: PolicySearchQuery,
        candidates: Sequence[PolicyClauseRecord],
        profile: LexicalProfile,
    ) -> tuple[PolicySearchHit, ...]:
        if not candidates:
            return ()
        query_terms = Counter(self._tokenizer.tokenize(query.query))
        documents = tuple(self._tokenizer.tokenize(_lexical_text(item)) for item in candidates)
        document_frequencies = Counter(
            term for document in documents for term in frozenset(document) if term in query_terms
        )
        average_length = sum(len(document) for document in documents) / len(documents)
        scored: list[tuple[float, PolicyClauseRecord]] = []
        for clause, tokens in zip(candidates, documents, strict=True):
            frequencies = Counter(tokens)
            score = 0.0
            for term, query_frequency in query_terms.items():
                term_frequency = frequencies[term]
                if term_frequency == 0:
                    continue
                document_frequency = document_frequencies[term]
                inverse_document_frequency = math.log(
                    1.0 + (len(documents) - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                length_normalization = 1.0 - profile.b
                if average_length > 0:
                    length_normalization += profile.b * len(tokens) / average_length
                denominator = term_frequency + profile.k1 * length_normalization
                score += (
                    inverse_document_frequency
                    * term_frequency
                    * (profile.k1 + 1.0)
                    / denominator
                    * query_frequency
                )
            if score > 0:
                scored.append((score, clause))
        scored.sort(key=lambda item: (-item[0], item[1].dedupe_key))
        return tuple(
            PolicySearchHit(clause=clause, lexical_rank=rank, lexical_score=score)
            for rank, (score, clause) in enumerate(scored[: query.top_k], start=1)
        )


def _lexical_text(clause: PolicyClauseRecord) -> str:
    return " ".join(
        (
            clause.title,
            *clause.section_path,
            clause.policy_type,
            clause.clause_type.value,
            *clause.product_categories,
            *clause.defect_types,
            *clause.actions,
            clause.clause_id,
            clause.text,
        )
    )


__all__ = ["ExactBM25Retriever", "KoreanPolicyTokenizerV1"]
