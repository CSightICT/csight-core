from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.platform import quantization_assets as assets
from app.platform.quantization_assets import (
    ChatMessage,
    ChatRole,
    CorpusSplit,
    MixCategory,
    NormalizedCorpusRecord,
    QuantizationAssetError,
    QuantizationCorpusManifest,
    QuantizationSourcePreparationManifestV1_1,
    build_quantization_corpus,
    canonical_digest,
)
from app.platform.quantization_assets import TestLeakageIndex as LeakageIndex
from app.platform.quantization_source_prep import (
    DatasetViewerPageAttestation,
    PublicDatasetFixtureAttestation,
    PublicDatasetRow,
    TokenizerRuntimeIdentity,
    build_corpus_plan,
    dataset_viewer_query_identity_digest,
    serialize_public_fixture,
    sha256_digest,
)
from scripts.build_qwen38_quantization_assets import (
    load_verified_source_preparation,
    write_quantization_corpus_v1_1,
)
from scripts.prepare_qwen38_quantization_sources import DEFAULT_REGISTRY, load_registry

pytestmark = pytest.mark.unit

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
LLAMA_CPP_REVISION = "aee56b3abfeb134218fe5c496c329a1faac1ef28"


class _CharacterTokenizer:
    identity_digest = DIGEST_A

    def encode(self, text: str) -> tuple[int, ...]:
        return tuple(ord(value) for value in text)

    def decode(self, token_ids: Sequence[int]) -> str:
        return "".join(chr(value) for value in token_ids)


def _plan():
    registry = load_registry(DEFAULT_REGISTRY)
    runtime = TokenizerRuntimeIdentity(
        identity_digest=DIGEST_A,
        gguf_tokenizer_metadata_digest=DIGEST_B,
        llama_cpp_revision=LLAMA_CPP_REVISION,
        implementation="llama.cpp b10419 GGUF tokenizer",
    )
    return build_corpus_plan(
        registry=registry,
        runtime_identity=runtime,
        test_reference_digests=tuple(
            item.revision
            for item in registry.mix
            if item.category
            not in {
                MixCategory.PUBLIC_KO_WIKIPEDIA,
                MixCategory.PUBLIC_EN_WIKITEXT,
            }
        ),
        seed="corpus-source-binding-unit-seed",
    )


def _records(plan: assets.QuantizationCorpusPlan) -> tuple[NormalizedCorpusRecord, ...]:
    records: list[NormalizedCorpusRecord] = []
    public_categories = {
        MixCategory.PUBLIC_KO_WIKIPEDIA,
        MixCategory.PUBLIC_EN_WIKITEXT,
    }
    for category_index, category in enumerate(MixCategory):
        pin = next(item for item in plan.sources if item.category is category)
        for record_index in range(4):
            records.append(
                NormalizedCorpusRecord(
                    record_id=f"B-{category_index}-{record_index}",
                    source_id=pin.source_id,
                    source_revision=pin.revision,
                    category=category,
                    license_identifier=pin.license_identifier,
                    pii_reviewed=True,
                    source_partition=(
                        "PUBLIC_TRAIN" if category in public_categories else "SYNTHETIC_TRAIN"
                    ),
                    messages=(
                        ChatMessage(
                            role=ChatRole.USER,
                            content=(
                                f"binding-{category_index}-{record_index}-"
                                + chr(65 + category_index) * 500
                            ),
                        ),
                    ),
                )
            )
    return tuple(records)


def _records_payload(records: Sequence[NormalizedCorpusRecord]) -> bytes:
    return "".join(
        json.dumps(
            item.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
        for item in records
    ).encode()


def _write_source_bundle(
    root: Path,
) -> tuple[assets.QuantizationCorpusPlan, Path, Path, tuple[Path, Path]]:
    plan = _plan()
    records = _records(plan)
    synthetic = tuple(
        item
        for item in records
        if item.category
        not in {
            MixCategory.PUBLIC_KO_WIKIPEDIA,
            MixCategory.PUBLIC_EN_WIKITEXT,
        }
    )
    public = tuple(item for item in records if item not in synthetic)
    plan_path = root / "corpus_plan.json"
    synthetic_path = root / "csight_synthetic_train.jsonl"
    public_path = root / "public_train.jsonl"
    plan_payload = (
        json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode()
    synthetic_payload = _records_payload(synthetic)
    public_payload = _records_payload(public)
    plan_path.write_bytes(plan_payload)
    synthetic_path.write_bytes(synthetic_payload)
    public_path.write_bytes(public_payload)

    public_dir = root / "public_sources"
    public_dir.mkdir()
    attestation_entries: list[dict[str, object]] = []
    for category in sorted(
        (MixCategory.PUBLIC_KO_WIKIPEDIA, MixCategory.PUBLIC_EN_WIKITEXT),
        key=lambda item: item.value,
    ):
        pin = next(item for item in plan.sources if item.category is category)
        assert pin.config is not None
        assert pin.split is not None
        rows = (PublicDatasetRow(row_index=0, values={"text": f"fixture-{category.value}"}),)
        fixture_payload = serialize_public_fixture(rows)
        page = DatasetViewerPageAttestation(
            offset=0,
            length=1,
            row_count=1,
            response_revision=pin.revision,
            response_body_digest="sha256:" + "c" * 64,
            response_body_bytes=123,
            canonical_rows_digest=sha256_digest(fixture_payload),
            canonical_rows_bytes=len(fixture_payload),
        )
        query_digest = dataset_viewer_query_identity_digest(
            source_id=pin.source_id,
            source_revision=pin.revision,
            config=pin.config,
            split=pin.split,
            requested_maximum_rows=1,
            page_size=1,
            pages=(page,),
        )
        attestation = PublicDatasetFixtureAttestation(
            source_id=pin.source_id,
            source_revision=pin.revision,
            config=pin.config,
            split=pin.split,
            requested_maximum_rows=1,
            page_size=1,
            fixture_payload_digest=sha256_digest(fixture_payload),
            fixture_payload_bytes=len(fixture_payload),
            fixture_row_count=1,
            query_identity_digest=query_digest,
            pages=(page,),
        )
        stem = category.value.casefold()
        fixture_path = public_dir / f"{stem}.rows.jsonl"
        attestation_path = public_dir / f"{stem}.attestation.json"
        attestation_payload = (
            json.dumps(
                attestation.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()
        fixture_path.write_bytes(fixture_payload)
        attestation_path.write_bytes(attestation_payload)
        attestation_entries.append(
            {
                "attestation_digest": sha256_digest(attestation_payload),
                "attestation_path": str(attestation_path.relative_to(root)),
                "category": category.value,
                "fixture_digest": sha256_digest(fixture_payload),
                "fixture_path": str(fixture_path.relative_to(root)),
                "query_identity_digest": query_digest,
                "source_id": pin.source_id,
                "source_revision": pin.revision,
            }
        )

    counts = {category: 0 for category in MixCategory}
    for record in records:
        counts[record.category] += 1
    stats = []
    for category in MixCategory:
        required = sum(plan.target_for(split, category) for split in CorpusSplit)
        stats.append(
            {
                "category": category.value,
                "record_count": counts[category],
                "screened_token_count": required + 100,
                "required_token_count": required,
                "source_partition": (
                    "PUBLIC_TRAIN"
                    if category
                    in {
                        MixCategory.PUBLIC_KO_WIKIPEDIA,
                        MixCategory.PUBLIC_EN_WIKITEXT,
                    }
                    else "SYNTHETIC_TRAIN"
                ),
            }
        )
    manifest = {
        "schema_version": "quantization_source_preparation_manifest/1.1.0",
        "plan_digest": canonical_digest(plan),
        "generator_version": "csight-qwen38-source-generator/1.0.0",
        "files": {
            "corpus_plan.json": sha256_digest(plan_payload),
            "csight_synthetic_train.jsonl": sha256_digest(synthetic_payload),
            "public_train.jsonl": sha256_digest(public_payload),
        },
        "stats": stats,
        "public_categories_ready": sorted(
            item.value
            for item in {
                MixCategory.PUBLIC_KO_WIKIPEDIA,
                MixCategory.PUBLIC_EN_WIKITEXT,
            }
        ),
        "public_source_attestations": attestation_entries,
        "public_source_capture_scope": "LOCAL_PROVENANCE_ONLY_NOT_MODEL_ARTIFACT",
        "public_source_captures_pii_screened": False,
        "normalized_outputs_pii_screened": True,
        "raw_customer_data_used": False,
        "direct_identifiers_present": False,
        "sealed_test_records_used": False,
        "model_calls_performed": 0,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return plan, plan_path, manifest_path, (synthetic_path, public_path)


def _load_bundle(root: Path):
    plan, plan_path, manifest_path, input_paths = _write_source_bundle(root)
    return (
        load_verified_source_preparation(
            manifest_path=manifest_path,
            plan=plan,
            plan_payload=plan_path.read_bytes(),
            input_paths=tuple(reversed(input_paths)),
        ),
        plan,
        manifest_path,
        input_paths,
    )


def test_source_preparation_v11_binds_exact_normalized_and_public_capture_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        assets,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 600, "PPL_HOLDOUT": 600, "LOGITS_HOLDOUT": 600},
    )
    bundle, _plan_value, manifest_path, _input_paths = _load_bundle(tmp_path)

    assert bundle.manifest_content_digest == sha256_digest(manifest_path.read_bytes())
    assert set(bundle.manifest.public_categories_ready) == {
        MixCategory.PUBLIC_KO_WIKIPEDIA,
        MixCategory.PUBLIC_EN_WIKITEXT,
    }
    assert len(bundle.manifest.public_source_attestations) == 2
    assert len(bundle.records) == 24


def test_source_preparation_v11_rejects_normalized_input_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        assets,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 600, "PPL_HOLDOUT": 600, "LOGITS_HOLDOUT": 600},
    )
    plan, plan_path, manifest_path, input_paths = _write_source_bundle(tmp_path)
    input_paths[1].write_bytes(input_paths[1].read_bytes() + b"\n")

    with pytest.raises(QuantizationAssetError, match="normalized input digest"):
        load_verified_source_preparation(
            manifest_path=manifest_path,
            plan=plan,
            plan_payload=plan_path.read_bytes(),
            input_paths=input_paths,
        )


def test_source_preparation_v11_requires_both_categories_and_safe_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        assets,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 600, "PPL_HOLDOUT": 600, "LOGITS_HOLDOUT": 600},
    )
    _plan_value, _plan_path, manifest_path, _input_paths = _write_source_bundle(tmp_path)
    payload = json.loads(manifest_path.read_text())
    assert isinstance(payload, dict)
    payload["public_categories_ready"] = ["PUBLIC_EN_WIKITEXT"]
    payload["normalized_outputs_pii_screened"] = False

    with pytest.raises(ValidationError):
        QuantizationSourcePreparationManifestV1_1.model_validate(payload)


def test_source_preparation_v11_rejects_attestation_sidecar_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        assets,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 600, "PPL_HOLDOUT": 600, "LOGITS_HOLDOUT": 600},
    )
    plan, plan_path, manifest_path, input_paths = _write_source_bundle(tmp_path)
    payload = json.loads(manifest_path.read_text())
    assert isinstance(payload, dict)
    entries = payload["public_source_attestations"]
    assert isinstance(entries, list)
    first = entries[0]
    assert isinstance(first, dict)
    attestation_path = tmp_path / str(first["attestation_path"])
    attestation_path.write_bytes(attestation_path.read_bytes() + b"\n")

    with pytest.raises(QuantizationAssetError, match="public attestation digest"):
        load_verified_source_preparation(
            manifest_path=manifest_path,
            plan=plan,
            plan_payload=plan_path.read_bytes(),
            input_paths=input_paths,
        )


def test_corpus_v11_records_source_manifest_digest_and_preserves_v10_read_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        assets,
        "_SPLIT_TOKEN_TARGETS",
        {"CALIBRATION": 600, "PPL_HOLDOUT": 600, "LOGITS_HOLDOUT": 600},
    )
    bundle, plan, manifest_path, _input_paths = _load_bundle(tmp_path)
    tokenizer = _CharacterTokenizer()
    build = build_quantization_corpus(
        plan=plan,
        records=bundle.records,
        tokenizer=tokenizer,
        test_leakage_index=LeakageIndex(("unrelated sealed Test sentence",)),
    )

    corpus = write_quantization_corpus_v1_1(
        output_dir=tmp_path / "corpus-v1.1",
        plan=plan,
        build=build,
        tokenizer=tokenizer,
        source_preparation=bundle,
    )

    assert corpus.schema_version == "quantization_corpus_manifest/1.1.0"
    assert corpus.source_preparation_manifest_digest == sha256_digest(manifest_path.read_bytes())
    assert len(corpus.source_preparation.public_source_attestations) == 2
    tampered = corpus.model_dump(mode="json")
    tampered["source_preparation"]["files"]["public_train.jsonl"] = "sha256:" + "f" * 64
    with pytest.raises(ValidationError, match="digest does not match"):
        assets.QuantizationCorpusManifestV1_1.model_validate(tampered)
    legacy_payload = corpus.model_dump(mode="json")
    legacy_payload["schema_version"] = "quantization_corpus_manifest/1.0.0"
    legacy_payload.pop("source_preparation_manifest_digest")
    legacy_payload.pop("source_preparation")
    legacy = QuantizationCorpusManifest.model_validate(legacy_payload)
    assert legacy.schema_version == "quantization_corpus_manifest/1.0.0"
    with pytest.raises(QuantizationAssetError, match="overwrite"):
        write_quantization_corpus_v1_1(
            output_dir=tmp_path / "corpus-v1.1",
            plan=plan,
            build=build,
            tokenizer=tokenizer,
            source_preparation=bundle,
        )
