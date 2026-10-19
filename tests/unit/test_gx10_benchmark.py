from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/benchmark_gx10_llama_cpp.py"
SPEC = importlib.util.spec_from_file_location("benchmark_gx10_llama_cpp", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


def test_percentile_uses_nearest_rank() -> None:
    assert benchmark.percentile([5.0, 1.0, 4.0, 2.0, 3.0], 0.95) == 5.0
    assert benchmark.percentile([], 0.95) is None


def test_summary_contains_only_metrics_and_stable_prompt_digest() -> None:
    samples = [
        benchmark.Sample(1000.0, 200.0, 3500, 80, True, False, True, None),
        benchmark.Sample(1200.0, 240.0, 3500, 96, True, False, True, None),
    ]
    sampler = benchmark.ResourceSampler()
    sampler.gpu_used = [20_000_000_000, 21_000_000_000]
    sampler.system_used = [30_000_000_000]
    sampler.temperatures = [44.0, 45.0]
    sampler.power_watts = [90.0]
    report = benchmark.summarize(
        samples=samples,
        wall_seconds=2.0,
        context_per_slot=4096,
        configured_total_context=8192,
        concurrency=2,
        requests_count=2,
        warmup_count=1,
        prompt_tokens=3400,
        prompt_digest="a" * 64,
        sampler=sampler,
    )

    assert report["success_rate"] == 1.0
    assert report["ttft_ms_p95"] == 240.0
    assert report["latency_ms_p95"] == 1200.0
    assert report["decode_tokens_per_second"] == pytest.approx(100.0)
    assert report["wall_output_tokens_per_second"] == 88.0
    assert report["peak_unified_memory_bytes"] == 21_000_000_000
    assert report["prompt_digest"] == f"sha256:{'a' * 64}"
    assert "prompt" not in report
    assert "response" not in report
