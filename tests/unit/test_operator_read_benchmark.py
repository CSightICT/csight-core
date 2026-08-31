"""Unit checks for the local read-only operator baseline collector."""

import pytest

from scripts.benchmark_operator_reads import nearest_rank_percentile

pytestmark = pytest.mark.unit


def test_nearest_rank_percentile_is_deterministic() -> None:
    assert nearest_rank_percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.50) == 3.0
    assert nearest_rank_percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.95) == 5.0


def test_percentile_requires_a_sample() -> None:
    with pytest.raises(ValueError, match="at least one"):
        nearest_rank_percentile([], 0.95)
