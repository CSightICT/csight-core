from __future__ import annotations

import json
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from urllib3.response import BaseHTTPResponse, HTTPResponse

from app.adapters.datasets import HuggingFaceDatasetViewerRows
from app.platform import quantization_assets
from app.platform.quantization_assets import (
    CorpusSplit,
    MixCategory,
    NormalizedCorpusRecord,
    PreparedCorpusSample,
    QuantizationAssetError,
    SourcePin,
    pii_finding_codes,
    render_qwen38_text_chat,
)
from app.platform.quantization_assets import TestLeakageIndex as LeakageIndex
from app.platform.quantization_source_prep import (
    AttestedPublicDatasetRows,
    DatasetViewerPageAttestation,
    PublicDatasetFixtureAttestation,
    PublicDatasetRow,
    QuantizationSourceRegistry,
    TokenizerRuntimeIdentity,
    build_corpus_plan,
    dataset_viewer_query_identity_digest,
    generate_csight_synthetic_sources,
    normalize_public_rows,
    required_tokens,
    serialize_public_fixture,
    sha256_digest,
)
from scripts.prepare_qwen38_quantization_sources import (
    DEFAULT_LOCAL_SOURCE_REFERENCES,
    DEFAULT_REGISTRY,
    PreparedPublicSource,
    load_attested_public_fixture,
    load_registry,
    load_test_references,
    validate_local_source_revisions,
    validate_public_fixture_pairs,
    write_prepared_assets,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
LLAMA_REVISION = "1" * 40


class _CharacterTokenizer:
    def __init__(self, identity_digest: str = DIGEST_A) -> None:
        self._identity_digest = identity_digest

    @property
    def identity_digest(self) -> str:
        return self._identity_digest

    def encode(self, text: str) -> tuple[int, ...]:
        return tuple(ord(item) for item in text)

    def decode(self, token_ids: Sequence[int]) -> str:
        return "".join(chr(item) for item in token_ids)


def _runtime() -> TokenizerRuntimeIdentity:
    return TokenizerRuntimeIdentity(
        identity_digest=DIGEST_A,
        gguf_tokenizer_metadata_digest=DIGEST_B,
        llama_cpp_revision=LLAMA_REVISION,
        implementation="llama.cpp b10419 GGUF tokenizer",
    )


def _plan(registry: QuantizationSourceRegistry | None = None):
    registry = registry or load_registry(DEFAULT_REGISTRY)
    return build_corpus_plan(
        registry=registry,
        runtime_identity=_runtime(),
        test_reference_digests=tuple(
            item.revision
            for item in registry.mix
            if item.category
            in {
                MixCategory.CSIGHT_EXTRACTION,
                MixCategory.CSIGHT_POLICY_GROUNDING,
                MixCategory.CSIGHT_QUERY_BUILDER,
                MixCategory.CSIGHT_SAFETY_JSON_INJECTION,
            }
        ),
        seed="fixed-source-preparation-seed",
    )


def _attested_rows(
    *,
    source: SourcePin,
    rows: tuple[PublicDatasetRow, ...],
    maximum_rows: int,
    page_size: int | None = None,
) -> AttestedPublicDatasetRows:
    effective_page_size = page_size or maximum_rows
    page_payload = serialize_public_fixture(rows)
    page = DatasetViewerPageAttestation(
        offset=0,
        length=min(effective_page_size, maximum_rows),
        row_count=len(rows),
        response_revision=source.revision,
        response_body_digest="sha256:" + "c" * 64,
        response_body_bytes=123,
        canonical_rows_digest=sha256_digest(page_payload),
        canonical_rows_bytes=len(page_payload),
    )
    config = source.config
    split = source.split
    assert config is not None
    assert split is not None
    query_digest = dataset_viewer_query_identity_digest(
        source_id=source.source_id,
        source_revision=source.revision,
        config=config,
        split=split,
        requested_maximum_rows=maximum_rows,
        page_size=effective_page_size,
        pages=(page,),
    )
    return AttestedPublicDatasetRows(
        rows=rows,
        attestation=PublicDatasetFixtureAttestation(
            source_id=source.source_id,
            source_revision=source.revision,
            config=config,
            split=split,
            requested_maximum_rows=maximum_rows,
            page_size=effective_page_size,
            fixture_payload_digest=sha256_digest(page_payload),
            fixture_payload_bytes=len(page_payload),
            fixture_row_count=len(rows),
            query_identity_digest=query_digest,
            pages=(page,),
        ),
    )


def test_plan_binds_exact_runtime_test_files_and_public_revisions() -> None:
    plan = _plan()

    assert plan.chat_template.tokenizer_runtime_identity_digest == DIGEST_A
    assert plan.chat_template.gguf_tokenizer_metadata_digest == DIGEST_B
    assert plan.chat_template.llama_cpp_revision == LLAMA_REVISION
    assert plan.test_reference_digests == tuple(sorted(plan.test_reference_digests))
    public = {item.category: item for item in plan.sources if item.config is not None}
    assert public[MixCategory.PUBLIC_KO_WIKIPEDIA].revision == (
        "b04c8d1ceb2f5cd4588862100d08de323dccfbaa"
    )
    assert public[MixCategory.PUBLIC_EN_WIKITEXT].revision == (
        "b08601e04326c79dfdd32d625aee71d232d685c3"
    )


def test_plan_rejects_a_replaced_test_reference_digest() -> None:
    registry = load_registry(DEFAULT_REGISTRY)
    expected = [
        item.revision
        for item in registry.mix
        if item.category
        in {
            MixCategory.CSIGHT_EXTRACTION,
            MixCategory.CSIGHT_POLICY_GROUNDING,
            MixCategory.CSIGHT_QUERY_BUILDER,
            MixCategory.CSIGHT_SAFETY_JSON_INJECTION,
        }
    ]
    expected[-1] = "sha256:" + "9" * 64

    with pytest.raises(QuantizationAssetError, match="four exact"):
        build_corpus_plan(
            registry=registry,
            runtime_identity=_runtime(),
            test_reference_digests=expected,
            seed="fixed-source-preparation-seed",
        )


def test_prepared_sample_preserves_token_counted_trailing_chat_delimiter() -> None:
    plan = _plan()
    prepared = generate_csight_synthetic_sources(
        plan=plan,
        tokenizer=_CharacterTokenizer(),
        test_leakage_index=LeakageIndex(("unrelated sealed reference phrase",)),
    )
    record = prepared.records[0]
    rendered = render_qwen38_text_chat(record.messages)
    tokenizer = _CharacterTokenizer()

    sample = PreparedCorpusSample(
        record_id_hash="sha256:" + "e" * 64,
        source_id=record.source_id,
        source_revision=record.source_revision,
        category=record.category,
        split=CorpusSplit.CALIBRATION,
        token_count=len(tokenizer.encode(rendered)),
        content_digest="sha256:" + "f" * 64,
        text=rendered,
    )

    assert rendered.endswith("<|im_end|>\n")
    assert sample.text == rendered
    assert len(tokenizer.encode(sample.text)) == sample.token_count


def test_csight_generator_fills_exact_866k_mix_without_test_or_pii() -> None:
    plan = _plan()
    tokenizer = _CharacterTokenizer()
    sealed_phrase = "sealed Test phrase that must never enter a generated conversation"
    prepared = generate_csight_synthetic_sources(
        plan=plan,
        tokenizer=tokenizer,
        test_leakage_index=LeakageIndex((sealed_phrase,)),
    )

    assert {item.category: item.required_token_count for item in prepared.stats} == {
        MixCategory.CSIGHT_EXTRACTION: 303_100,
        MixCategory.CSIGHT_POLICY_GROUNDING: 173_200,
        MixCategory.CSIGHT_QUERY_BUILDER: 86_600,
        MixCategory.CSIGHT_SAFETY_JSON_INJECTION: 86_600,
    }
    assert sum(item.required_token_count for item in prepared.stats) == 649_500
    assert all(item.screened_token_count >= item.required_token_count for item in prepared.stats)
    assert prepared.sealed_test_records_used is False
    assert prepared.raw_customer_data_used is False
    assert prepared.model_calls_performed == 0
    assert {item.source_partition for item in prepared.records} == {"SYNTHETIC_TRAIN"}
    rendered = tuple(render_qwen38_text_chat(item.messages) for item in prepared.records)
    assert all(not pii_finding_codes(item) for item in rendered)
    assert all(sealed_phrase not in item for item in rendered)
    assert len(rendered) == len(set(rendered))


def test_csight_generator_is_deterministic_with_fixed_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        quantization_assets,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 1200, "PPL_HOLDOUT": 600, "LOGITS_HOLDOUT": 600},
    )
    plan = _plan()
    tokenizer = _CharacterTokenizer()
    leakage_index = LeakageIndex(("unrelated sealed reference phrase",))

    first = generate_csight_synthetic_sources(
        plan=plan,
        tokenizer=tokenizer,
        test_leakage_index=leakage_index,
    )
    second = generate_csight_synthetic_sources(
        plan=plan,
        tokenizer=tokenizer,
        test_leakage_index=leakage_index,
    )

    assert first == second


def test_public_rows_are_injected_offline_and_screened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        quantization_assets,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 200, "PPL_HOLDOUT": 100, "LOGITS_HOLDOUT": 100},
    )
    plan = _plan()
    source = next(item for item in plan.sources if item.category is MixCategory.PUBLIC_EN_WIKITEXT)
    fixtures = tuple(
        PublicDatasetRow(
            row_index=index,
            values={"text": f"Offline public fixture {index}: " + chr(65 + index) * 600},
        )
        for index in range(8)
    )

    prepared = normalize_public_rows(
        plan=plan,
        source=source,
        attested_rows=_attested_rows(source=source, rows=fixtures, maximum_rows=8),
        maximum_rows=8,
        tokenizer=_CharacterTokenizer(),
        test_leakage_index=LeakageIndex(("sealed reference that differs from fixtures",)),
    )

    assert prepared.stats[0].required_token_count == required_tokens(
        plan, MixCategory.PUBLIC_EN_WIKITEXT
    )
    assert {item.source_partition for item in prepared.records} == {"PUBLIC_TRAIN"}
    assert all(item.pii_reviewed for item in prepared.records)


class _FakeDatasetViewerHTTP:
    def __init__(self, revision: str, *, partial: bool = False) -> None:
        self.revision = revision
        self.partial = partial
        self.urls: list[str] = []

    def request(self, method: str, url: str, **urlopen_kw: Any) -> BaseHTTPResponse:
        del urlopen_kw
        assert method == "GET"
        self.urls.append(url)
        query = parse_qs(urlsplit(url).query)
        offset = int(query["offset"][0])
        length = int(query["length"][0])
        rows = [
            {
                "row_idx": offset + index,
                "row": {"text": f"fixture row {offset + index}"},
                "truncated_cells": [],
            }
            for index in range(length)
        ]
        return HTTPResponse(
            body=json.dumps({"partial": self.partial, "rows": rows}).encode(),
            status=200,
            headers={"x-revision": self.revision},
        )


def test_dataset_viewer_adapter_attests_revision_without_real_network() -> None:
    source = next(
        item for item in _plan().sources if item.category is MixCategory.PUBLIC_EN_WIKITEXT
    )
    fake = _FakeDatasetViewerHTTP(source.revision)
    adapter = HuggingFaceDatasetViewerRows(page_size=2, http_client=fake)

    captured = adapter.fetch_attested_rows(source=source, maximum_rows=3)
    rows = captured.rows

    assert [item.row_index for item in rows] == [0, 1, 2]
    assert captured.attestation.source_revision == source.revision
    assert captured.attestation.fixture_payload_digest == sha256_digest(
        serialize_public_fixture(rows)
    )
    assert [item.response_revision for item in captured.attestation.pages] == [
        source.revision,
        source.revision,
    ]
    assert len(fake.urls) == 2
    assert all(parse_qs(urlsplit(url).query)["revision"] == [source.revision] for url in fake.urls)


def test_dataset_viewer_adapter_rejects_unattested_revision() -> None:
    source = next(
        item for item in _plan().sources if item.category is MixCategory.PUBLIC_KO_WIKIPEDIA
    )
    adapter = HuggingFaceDatasetViewerRows(
        page_size=1,
        http_client=_FakeDatasetViewerHTTP("0" * 40),
    )

    with pytest.raises(QuantizationAssetError, match="attest"):
        adapter.fetch_attested_rows(source=source, maximum_rows=1)


def test_dataset_viewer_adapter_rejects_partial_response() -> None:
    source = next(
        item for item in _plan().sources if item.category is MixCategory.PUBLIC_EN_WIKITEXT
    )
    adapter = HuggingFaceDatasetViewerRows(
        page_size=1,
        http_client=_FakeDatasetViewerHTTP(source.revision, partial=True),
    )

    with pytest.raises(QuantizationAssetError, match="partial response"):
        adapter.fetch_attested_rows(source=source, maximum_rows=1)


def test_attestation_rejects_incomplete_nonterminal_pagination() -> None:
    source = next(
        item for item in _plan().sources if item.category is MixCategory.PUBLIC_EN_WIKITEXT
    )
    rows = tuple(
        PublicDatasetRow(row_index=index, values={"text": f"row {index}"}) for index in range(2)
    )
    payload = serialize_public_fixture(rows)
    page = DatasetViewerPageAttestation(
        offset=0,
        length=2,
        row_count=2,
        response_revision=source.revision,
        response_body_digest="sha256:" + "d" * 64,
        response_body_bytes=100,
        canonical_rows_digest=sha256_digest(payload),
        canonical_rows_bytes=len(payload),
    )
    assert source.config is not None
    assert source.split is not None
    query_digest = dataset_viewer_query_identity_digest(
        source_id=source.source_id,
        source_revision=source.revision,
        config=source.config,
        split=source.split,
        requested_maximum_rows=4,
        page_size=2,
        pages=(page,),
    )

    with pytest.raises(ValueError, match="terminal page"):
        PublicDatasetFixtureAttestation(
            source_id=source.source_id,
            source_revision=source.revision,
            config=source.config,
            split=source.split,
            requested_maximum_rows=4,
            page_size=2,
            fixture_payload_digest=sha256_digest(payload),
            fixture_payload_bytes=len(payload),
            fixture_row_count=2,
            query_identity_digest=query_digest,
            pages=(page,),
        )


def test_offline_public_fixture_recomputes_payload_and_query_identity(tmp_path: Path) -> None:
    source = next(
        item for item in _plan().sources if item.category is MixCategory.PUBLIC_EN_WIKITEXT
    )
    rows = tuple(
        PublicDatasetRow(row_index=index, values={"text": f"public row {index}"})
        for index in range(3)
    )
    captured = _attested_rows(source=source, rows=rows, maximum_rows=3)
    fixture_path = tmp_path / "public.rows.jsonl"
    attestation_path = tmp_path / "public.attestation.json"
    fixture_path.write_bytes(serialize_public_fixture(rows))
    attestation_path.write_text(captured.attestation.model_dump_json(), encoding="utf-8")

    replayed = load_attested_public_fixture(
        fixture_path=fixture_path,
        attestation_path=attestation_path,
        source=source,
        maximum_rows=3,
    )

    assert replayed == captured


def test_offline_public_fixture_rejects_payload_tampering(tmp_path: Path) -> None:
    source = next(
        item for item in _plan().sources if item.category is MixCategory.PUBLIC_EN_WIKITEXT
    )
    rows = (PublicDatasetRow(row_index=0, values={"text": "original public row"}),)
    captured = _attested_rows(source=source, rows=rows, maximum_rows=1)
    fixture_path = tmp_path / "public.rows.jsonl"
    attestation_path = tmp_path / "public.attestation.json"
    fixture_path.write_bytes(
        serialize_public_fixture(
            (PublicDatasetRow(row_index=0, values={"text": "tampered public row"}),)
        )
    )
    attestation_path.write_text(captured.attestation.model_dump_json(), encoding="utf-8")

    with pytest.raises(QuantizationAssetError, match="does not match"):
        load_attested_public_fixture(
            fixture_path=fixture_path,
            attestation_path=attestation_path,
            source=source,
            maximum_rows=1,
        )


def test_offline_public_fixture_rejects_query_bound_change(tmp_path: Path) -> None:
    source = next(
        item for item in _plan().sources if item.category is MixCategory.PUBLIC_EN_WIKITEXT
    )
    rows = (PublicDatasetRow(row_index=0, values={"text": "one public row"}),)
    captured = _attested_rows(source=source, rows=rows, maximum_rows=1)
    fixture_path = tmp_path / "public.rows.jsonl"
    attestation_path = tmp_path / "public.attestation.json"
    fixture_path.write_bytes(serialize_public_fixture(rows))
    attestation_path.write_text(captured.attestation.model_dump_json(), encoding="utf-8")

    with pytest.raises(QuantizationAssetError, match="query identity"):
        load_attested_public_fixture(
            fixture_path=fixture_path,
            attestation_path=attestation_path,
            source=source,
            maximum_rows=2,
        )


def test_offline_public_fixture_rejects_config_identity_change(tmp_path: Path) -> None:
    source = next(
        item for item in _plan().sources if item.category is MixCategory.PUBLIC_EN_WIKITEXT
    )
    rows = (PublicDatasetRow(row_index=0, values={"text": "one public row"}),)
    captured = _attested_rows(source=source, rows=rows, maximum_rows=1)
    altered_config = "unapproved-config"
    altered_query_digest = dataset_viewer_query_identity_digest(
        source_id=source.source_id,
        source_revision=source.revision,
        config=altered_config,
        split=captured.attestation.split,
        requested_maximum_rows=1,
        page_size=1,
        pages=captured.attestation.pages,
    )
    altered_attestation = captured.attestation.model_copy(
        update={
            "config": altered_config,
            "query_identity_digest": altered_query_digest,
        }
    )
    fixture_path = tmp_path / "public.rows.jsonl"
    attestation_path = tmp_path / "public.attestation.json"
    fixture_path.write_bytes(serialize_public_fixture(rows))
    attestation_path.write_text(altered_attestation.model_dump_json(), encoding="utf-8")

    with pytest.raises(QuantizationAssetError, match="query identity"):
        load_attested_public_fixture(
            fixture_path=fixture_path,
            attestation_path=attestation_path,
            source=source,
            maximum_rows=1,
        )


def test_public_fixture_and_attestation_arguments_are_paired_by_category() -> None:
    fixture = {MixCategory.PUBLIC_EN_WIKITEXT: Path("/tmp/public.rows.jsonl")}
    attestation = {MixCategory.PUBLIC_EN_WIKITEXT: Path("/tmp/public.attestation.json")}

    assert set(fixture) == set(attestation) == {MixCategory.PUBLIC_EN_WIKITEXT}

    with pytest.raises(QuantizationAssetError, match="matching Dataset Viewer attestation"):
        validate_public_fixture_pairs(fixture, {})


def test_tracked_references_are_digest_pinned_and_test_only_index_is_loaded() -> None:
    registry = load_registry(DEFAULT_REGISTRY)
    validate_local_source_revisions(registry)
    digests, leakage = load_test_references(tuple(DEFAULT_LOCAL_SOURCE_REFERENCES.values()))

    assert set(digests) == {
        item.revision
        for item in registry.mix
        if item.category
        in {
            MixCategory.CSIGHT_EXTRACTION,
            MixCategory.CSIGHT_POLICY_GROUNDING,
            MixCategory.CSIGHT_QUERY_BUILDER,
            MixCategory.CSIGHT_SAFETY_JSON_INJECTION,
        }
    }
    test_row = next(
        json.loads(line)
        for line in (ROOT / "evaluation/prompt_injection_v1/gold.jsonl").read_text().splitlines()
        if json.loads(line)["split"] == "test"
    )
    assert leakage.overlaps(test_row["customer_message"])


def test_writer_is_deterministic_and_refuses_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        quantization_assets,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 1200, "PPL_HOLDOUT": 600, "LOGITS_HOLDOUT": 600},
    )
    plan = _plan()
    synthetic = generate_csight_synthetic_sources(
        plan=plan,
        tokenizer=_CharacterTokenizer(),
        test_leakage_index=LeakageIndex(("isolated Test reference phrase",)),
    )
    output = tmp_path / "prepared"

    manifest = write_prepared_assets(
        output_dir=output,
        plan=plan,
        synthetic=synthetic,
        public=(),
    )

    assert manifest["model_calls_performed"] == 0
    assert manifest["sealed_test_records_used"] is False
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir() if path.is_file()
    )
    records = tuple(
        NormalizedCorpusRecord.model_validate_json(line)
        for line in (output / "csight_synthetic_train.jsonl").read_text().splitlines()
    )
    assert len(records) == len(synthetic.records)
    with pytest.raises(QuantizationAssetError, match="overwrite"):
        write_prepared_assets(
            output_dir=output,
            plan=plan,
            synthetic=synthetic,
            public=(),
        )


def test_writer_rejects_permissive_existing_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        quantization_assets,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 1200, "PPL_HOLDOUT": 600, "LOGITS_HOLDOUT": 600},
    )
    plan = _plan()
    synthetic = generate_csight_synthetic_sources(
        plan=plan,
        tokenizer=_CharacterTokenizer(),
        test_leakage_index=LeakageIndex(("isolated Test reference phrase",)),
    )
    output = tmp_path / "permissive"
    output.mkdir(mode=0o755)
    output.chmod(0o755)

    with pytest.raises(QuantizationAssetError, match="owner-only mode 0700"):
        write_prepared_assets(
            output_dir=output,
            plan=plan,
            synthetic=synthetic,
            public=(),
        )

    assert tuple(output.iterdir()) == ()


def test_writer_refuses_symlink_target_without_following_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        quantization_assets,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 1200, "PPL_HOLDOUT": 600, "LOGITS_HOLDOUT": 600},
    )
    plan = _plan()
    synthetic = generate_csight_synthetic_sources(
        plan=plan,
        tokenizer=_CharacterTokenizer(),
        test_leakage_index=LeakageIndex(("isolated Test reference phrase",)),
    )
    output = tmp_path / "prepared"
    output.mkdir(mode=0o700)
    output.chmod(0o700)
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_text("unchanged", encoding="utf-8")
    (output / "corpus_plan.json").symlink_to(unrelated)

    with pytest.raises(QuantizationAssetError, match="overwrite"):
        write_prepared_assets(
            output_dir=output,
            plan=plan,
            synthetic=synthetic,
            public=(),
        )

    assert unrelated.read_text(encoding="utf-8") == "unchanged"


def test_writer_emits_attested_public_capture_sidecars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        quantization_assets,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 200, "PPL_HOLDOUT": 100, "LOGITS_HOLDOUT": 100},
    )
    plan = _plan()
    tokenizer = _CharacterTokenizer()
    leakage_index = LeakageIndex(("isolated Test reference phrase",))
    synthetic = generate_csight_synthetic_sources(
        plan=plan,
        tokenizer=tokenizer,
        test_leakage_index=leakage_index,
    )
    source = next(item for item in plan.sources if item.category is MixCategory.PUBLIC_EN_WIKITEXT)
    rows = tuple(
        PublicDatasetRow(
            row_index=index,
            values={"text": f"Attested public fixture {index}: " + chr(65 + index) * 600},
        )
        for index in range(8)
    )
    captured = _attested_rows(source=source, rows=rows, maximum_rows=8)
    prepared = normalize_public_rows(
        plan=plan,
        source=source,
        attested_rows=captured,
        maximum_rows=8,
        tokenizer=tokenizer,
        test_leakage_index=leakage_index,
    )
    output = tmp_path / "prepared"

    manifest = write_prepared_assets(
        output_dir=output,
        plan=plan,
        synthetic=synthetic,
        public=(PreparedPublicSource(prepared=prepared, attested_rows=captured),),
    )

    assert manifest["schema_version"] == "quantization_source_preparation_manifest/1.1.0"
    entries = manifest["public_source_attestations"]
    assert isinstance(entries, list)
    assert len(entries) == 1
    entry = entries[0]
    assert isinstance(entry, Mapping)
    fixture_path = output / str(entry["fixture_path"])
    attestation_path = output / str(entry["attestation_path"])
    assert sha256_digest(fixture_path.read_bytes()) == entry["fixture_digest"]
    assert sha256_digest(attestation_path.read_bytes()) == entry["attestation_digest"]
    public_source_dir = output / "public_sources"
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE(public_source_dir.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.rglob("*") if path.is_file()
    )
