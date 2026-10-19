"""Prepare deterministic, PII-screened Qwen3.8 quantization sources and corpus plan."""

from __future__ import annotations

import argparse
import json
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.adapters.datasets import HuggingFaceDatasetViewerRows
from app.platform.quantization_assets import (
    MixCategory,
    NormalizedCorpusRecord,
    QuantizationAssetError,
    QuantizationCorpusPlan,
    SourcePin,
    TestLeakageIndex,
    TokenizerPort,
    canonical_digest,
    string_leaves,
)
from app.platform.quantization_source_prep import (
    AttestedPublicDatasetRows,
    PreparedNormalizedSources,
    PublicDatasetFixtureAttestation,
    PublicDatasetRow,
    QuantizationSourceRegistry,
    TokenizerRuntimeIdentity,
    build_corpus_plan,
    generate_csight_synthetic_sources,
    normalize_public_rows,
    serialize_public_fixture,
    sha256_digest,
    validate_attested_public_rows,
)
from app.ports.quantization_sources import PublicDatasetRowsPort

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "evaluation/llm/qwen38_quantization_v1/source_registry.json"
DEFAULT_OUTPUT = ROOT / "local-data/qwen38-27b-quantization/source-v1"
DEFAULT_SEED = "csight-qwen38-quantization-source-seed-20260831"
DEFAULT_LOCAL_SOURCE_REFERENCES = {
    "csight://evaluation/llm_extraction_v2": ROOT / "evaluation/llm_extraction_v2/gold.jsonl",
    "csight://evaluation/rag_grounding_v1": ROOT / "evaluation/rag_grounding_v1/gold.jsonl",
    "csight://evaluation/policy_query_builder_v1": (
        ROOT / "evaluation/policy_query_builder_v1/gold.jsonl"
    ),
    "csight://evaluation/prompt_injection_v1": (ROOT / "evaluation/prompt_injection_v1/gold.jsonl"),
}
_PUBLIC_CATEGORIES = (
    MixCategory.PUBLIC_KO_WIKIPEDIA,
    MixCategory.PUBLIC_EN_WIKITEXT,
)
_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_TOKENIZER_BYTES = 128 * 1024 * 1024
_MAX_TEST_REFERENCE_BYTES = 64 * 1024 * 1024
_MAX_PUBLIC_FIXTURE_BYTES = 512 * 1024 * 1024
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600


@dataclass(frozen=True)
class PreparedPublicSource:
    """A screened corpus slice plus the exact public capture that produced it."""

    prepared: PreparedNormalizedSources
    attested_rows: AttestedPublicDatasetRows


class PinnedTokenizerJsonAdapter:
    """Explicit offline adapter for the tokenizer bound by the runtime identity manifest."""

    def __init__(self, *, tokenizer_json: Path, identity_digest: str) -> None:
        try:
            from tokenizers import Tokenizer  # pyright: ignore[reportMissingImports]
        except ImportError as error:
            raise QuantizationAssetError(
                "tokenizers is required only for this explicit offline preparation command"
            ) from error
        _regular_file(tokenizer_json, maximum_bytes=_MAX_TOKENIZER_BYTES)
        self._tokenizer: Any = Tokenizer.from_file(str(tokenizer_json))
        self._identity_digest = identity_digest

    @property
    def identity_digest(self) -> str:
        return self._identity_digest

    def encode(self, text: str) -> tuple[int, ...]:
        return tuple(int(item) for item in self._tokenizer.encode(text).ids)

    def decode(self, token_ids: Sequence[int]) -> str:
        return str(self._tokenizer.decode(list(token_ids), skip_special_tokens=False))


def load_registry(path: Path) -> QuantizationSourceRegistry:
    try:
        return QuantizationSourceRegistry.model_validate_json(
            _regular_file(path, maximum_bytes=_MAX_JSON_BYTES)
        )
    except ValidationError as error:
        raise QuantizationAssetError(
            "quantization source registry failed strict validation"
        ) from error


def load_runtime_identity(path: Path) -> TokenizerRuntimeIdentity:
    try:
        return TokenizerRuntimeIdentity.model_validate_json(
            _regular_file(path, maximum_bytes=_MAX_JSON_BYTES)
        )
    except ValidationError as error:
        raise QuantizationAssetError(
            "tokenizer runtime identity failed strict validation"
        ) from error


def validate_tokenizer_config(path: Path, registry: QuantizationSourceRegistry) -> None:
    payload = _regular_file(path, maximum_bytes=_MAX_TOKENIZER_BYTES)
    if sha256_digest(payload) != registry.tokenizer_config_digest:
        raise QuantizationAssetError("tokenizer_config digest does not match the source registry")
    try:
        parsed = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QuantizationAssetError("tokenizer_config is not valid JSON") from error
    if not isinstance(parsed, Mapping) or not isinstance(parsed.get("chat_template"), str):
        raise QuantizationAssetError("tokenizer_config does not contain a string chat_template")
    if sha256_digest(parsed["chat_template"].encode()) != registry.chat_template_digest:
        raise QuantizationAssetError("chat_template digest does not match the source registry")


def validate_local_source_revisions(
    registry: QuantizationSourceRegistry,
    paths: Mapping[str, Path] = DEFAULT_LOCAL_SOURCE_REFERENCES,
) -> None:
    """Hash source artifacts only; their DEV/Test rows never feed the generator."""

    expected = {
        item.source_id: item.revision
        for item in registry.mix
        if item.category not in _PUBLIC_CATEGORIES
    }
    if set(paths) != set(expected):
        raise QuantizationAssetError("local source reference paths are incomplete")
    for source_id, path in paths.items():
        observed = sha256_digest(_regular_file(path, maximum_bytes=_MAX_TEST_REFERENCE_BYTES))
        if observed != expected[source_id]:
            raise QuantizationAssetError(f"local source revision mismatch for {source_id}")


def load_test_references(paths: Sequence[Path]) -> tuple[tuple[str, ...], TestLeakageIndex]:
    """Bind exact files and index only their sealed Test leaves for exclusion."""

    if len(paths) != 4 or len(set(paths)) != 4:
        raise QuantizationAssetError("exactly four unique Test reference files are required")
    digests: list[str] = []
    leaves: list[str] = []
    for path in paths:
        payload = _regular_file(path, maximum_bytes=_MAX_TEST_REFERENCE_BYTES)
        digests.append(sha256_digest(payload))
        test_rows = 0
        for line in payload.splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise QuantizationAssetError("Test reference contains invalid JSONL") from error
            if not isinstance(value, Mapping):
                raise QuantizationAssetError("Test reference row must be a JSON object")
            if str(value.get("split", "")).casefold() == "test":
                test_rows += 1
                leaves.extend(string_leaves(value))
        if test_rows == 0:
            raise QuantizationAssetError("each Test reference file must contain sealed Test rows")
    if len(digests) != len(set(digests)):
        raise QuantizationAssetError("Test reference content digests must be unique")
    return tuple(sorted(digests)), TestLeakageIndex(leaves)


def load_public_attestation(path: Path) -> PublicDatasetFixtureAttestation:
    try:
        return PublicDatasetFixtureAttestation.model_validate_json(
            _regular_file(path, maximum_bytes=_MAX_JSON_BYTES)
        )
    except ValidationError as error:
        raise QuantizationAssetError(
            "public Dataset Viewer attestation failed strict validation"
        ) from error


def load_attested_public_fixture(
    *,
    fixture_path: Path,
    attestation_path: Path,
    source: SourcePin,
    maximum_rows: int,
) -> AttestedPublicDatasetRows:
    """Recompute every offline fixture binding before any row reaches the corpus."""

    payload = _regular_file(fixture_path, maximum_bytes=_MAX_PUBLIC_FIXTURE_BYTES)
    rows: list[PublicDatasetRow] = []
    for line in payload.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise QuantizationAssetError("public fixture contains invalid JSONL") from error
        if not isinstance(value, Mapping):
            raise QuantizationAssetError("public fixture row must be a JSON object")
        if set(value) != {"row", "row_idx"}:
            raise QuantizationAssetError("public fixture must use canonical Dataset Viewer rows")
        wrapped_values = value.get("row")
        row_index = value.get("row_idx")
        if (
            not isinstance(row_index, int)
            or row_index < 0
            or not isinstance(wrapped_values, Mapping)
        ):
            raise QuantizationAssetError("public fixture row payload is invalid")
        rows.append(PublicDatasetRow(row_index=row_index, values=dict(wrapped_values)))
    canonical_payload = serialize_public_fixture(rows)
    if payload != canonical_payload:
        raise QuantizationAssetError("public fixture bytes are not canonical JSONL")
    attestation = load_public_attestation(attestation_path)
    try:
        result = AttestedPublicDatasetRows(rows=tuple(rows), attestation=attestation)
    except ValidationError as error:
        raise QuantizationAssetError(
            "public fixture payload does not match its Dataset Viewer attestation"
        ) from error
    validate_attested_public_rows(
        source=source,
        attested_rows=result,
        maximum_rows=maximum_rows,
    )
    return result


def prepare_public_sources(
    *,
    plan: QuantizationCorpusPlan,
    tokenizer: TokenizerPort,
    test_leakage_index: TestLeakageIndex,
    fixtures: Mapping[MixCategory, AttestedPublicDatasetRows],
    fetcher: PublicDatasetRowsPort | None,
    maximum_rows: int,
) -> tuple[PreparedPublicSource, ...]:
    results: list[PreparedPublicSource] = []
    pins = {item.category: item for item in plan.sources}
    for category in _PUBLIC_CATEGORIES:
        attested_rows = fixtures.get(category)
        if attested_rows is None and fetcher is not None:
            attested_rows = fetcher.fetch_attested_rows(
                source=pins[category], maximum_rows=maximum_rows
            )
        if attested_rows is None:
            continue
        results.append(
            PreparedPublicSource(
                prepared=normalize_public_rows(
                    plan=plan,
                    source=pins[category],
                    attested_rows=attested_rows,
                    maximum_rows=maximum_rows,
                    tokenizer=tokenizer,
                    test_leakage_index=test_leakage_index,
                ),
                attested_rows=attested_rows,
            )
        )
    return tuple(results)


def write_prepared_assets(
    *,
    output_dir: Path,
    plan: QuantizationCorpusPlan,
    synthetic: PreparedNormalizedSources,
    public: Sequence[PreparedPublicSource],
) -> Mapping[str, object]:
    _ensure_private_output_directory(output_dir)
    targets: dict[str, Path] = {
        "plan": output_dir / "corpus_plan.json",
        "synthetic": output_dir / "csight_synthetic_train.jsonl",
        "public": output_dir / "public_train.jsonl",
        "manifest": output_dir / "source_preparation_manifest.json",
    }
    public_source_dir = output_dir / "public_sources"
    if public_source_dir.is_symlink():
        raise QuantizationAssetError("public source directory must not be a symlink")
    public_targets: list[tuple[PreparedPublicSource, Path, Path]] = []
    observed_categories: set[MixCategory] = set()
    pins = {item.category: item for item in plan.sources}
    for bundle in public:
        if len(bundle.prepared.stats) != 1:
            raise QuantizationAssetError("each public source bundle requires exactly one category")
        category = bundle.prepared.stats[0].category
        if category not in _PUBLIC_CATEGORIES:
            raise QuantizationAssetError("public source bundle contains a non-public category")
        if category in observed_categories:
            raise QuantizationAssetError("public source categories must be unique")
        validate_attested_public_rows(
            source=pins[category],
            attested_rows=bundle.attested_rows,
            maximum_rows=bundle.attested_rows.attestation.requested_maximum_rows,
        )
        observed_categories.add(category)
        stem = category.value.casefold()
        fixture_target = public_source_dir / f"{stem}.rows.jsonl"
        attestation_target = public_source_dir / f"{stem}.attestation.json"
        public_targets.append((bundle, fixture_target, attestation_target))
        targets[f"{stem}_fixture"] = fixture_target
        targets[f"{stem}_attestation"] = attestation_target
    if (public_targets and public_source_dir.exists()) or any(
        path.exists() or path.is_symlink() for path in targets.values()
    ):
        raise QuantizationAssetError("refusing to overwrite existing prepared source assets")
    plan_text = (
        json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    synthetic_text = _records_jsonl(synthetic.records)
    public_records = tuple(record for bundle in public for record in bundle.prepared.records)
    public_text = _records_jsonl(public_records)
    if public_targets:
        _create_private_directory(public_source_dir)
    _write_private_file(targets["plan"], plan_text.encode("utf-8"))
    _write_private_file(targets["synthetic"], synthetic_text.encode("utf-8"))
    _write_private_file(targets["public"], public_text.encode("utf-8"))
    public_attestation_entries: list[Mapping[str, object]] = []
    for bundle, fixture_target, attestation_target in public_targets:
        fixture_payload = serialize_public_fixture(bundle.attested_rows.rows)
        attestation_text = (
            json.dumps(
                bundle.attested_rows.attestation.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        _write_private_file(fixture_target, fixture_payload)
        _write_private_file(attestation_target, attestation_text.encode("utf-8"))
        category = bundle.prepared.stats[0].category
        public_attestation_entries.append(
            {
                "attestation_digest": sha256_digest(attestation_text.encode()),
                "attestation_path": str(attestation_target.relative_to(output_dir)),
                "category": category.value,
                "fixture_digest": sha256_digest(fixture_payload),
                "fixture_path": str(fixture_target.relative_to(output_dir)),
                "query_identity_digest": (bundle.attested_rows.attestation.query_identity_digest),
                "source_id": bundle.attested_rows.attestation.source_id,
                "source_revision": bundle.attested_rows.attestation.source_revision,
            }
        )
    manifest: dict[str, object] = {
        "schema_version": "quantization_source_preparation_manifest/1.1.0",
        "plan_digest": canonical_digest(plan),
        "generator_version": synthetic.generator_version,
        "files": {
            "corpus_plan.json": sha256_digest(plan_text.encode()),
            "csight_synthetic_train.jsonl": sha256_digest(synthetic_text.encode()),
            "public_train.jsonl": sha256_digest(public_text.encode()),
        },
        "stats": [
            item.model_dump(mode="json")
            for item in (
                *synthetic.stats,
                *(stat for bundle in public for stat in bundle.prepared.stats),
            )
        ],
        "public_categories_ready": sorted(
            stat.category.value for bundle in public for stat in bundle.prepared.stats
        ),
        "public_source_attestations": sorted(
            public_attestation_entries,
            key=lambda item: str(item["category"]),
        ),
        "public_source_capture_scope": "LOCAL_PROVENANCE_ONLY_NOT_MODEL_ARTIFACT",
        "public_source_captures_pii_screened": False,
        "normalized_outputs_pii_screened": True,
        "raw_customer_data_used": False,
        "direct_identifiers_present": False,
        "sealed_test_records_used": False,
        "model_calls_performed": 0,
    }
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_private_file(targets["manifest"], manifest_text.encode("utf-8"))
    return manifest


def _ensure_private_output_directory(path: Path) -> None:
    if path.is_symlink():
        raise QuantizationAssetError("output directory must not be a symlink")
    if path.exists():
        try:
            metadata = path.stat(follow_symlinks=False)
        except OSError as error:
            raise QuantizationAssetError("cannot inspect output directory permissions") from error
        if not stat.S_ISDIR(metadata.st_mode):
            raise QuantizationAssetError("output path must be a directory")
        if stat.S_IMODE(metadata.st_mode) != _PRIVATE_DIRECTORY_MODE:
            raise QuantizationAssetError("existing output directory must be owner-only mode 0700")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _create_private_directory(path)


def _create_private_directory(path: Path) -> None:
    directory_flags = os.O_RDONLY
    directory_flags |= getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    parent_descriptor: int | None = None
    directory_descriptor: int | None = None
    try:
        parent_descriptor = os.open(path.parent, directory_flags)
        os.mkdir(path.name, _PRIVATE_DIRECTORY_MODE, dir_fd=parent_descriptor)
        directory_descriptor = os.open(
            path.name,
            directory_flags,
            dir_fd=parent_descriptor,
        )
        os.fchmod(directory_descriptor, _PRIVATE_DIRECTORY_MODE)
    except OSError as error:
        raise QuantizationAssetError(
            "failed to create owner-only source-preparation directory"
        ) from error
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def _write_private_file(path: Path, payload: bytes) -> None:
    directory_flags = os.O_RDONLY
    directory_flags |= getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    parent_descriptor: int | None = None
    try:
        parent_descriptor = os.open(path.parent, directory_flags)
        descriptor = os.open(
            path.name,
            flags,
            _PRIVATE_FILE_MODE,
            dir_fd=parent_descriptor,
        )
    except OSError as error:
        raise QuantizationAssetError("refusing to replace source-preparation asset") from error
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
    try:
        os.fchmod(descriptor, _PRIVATE_FILE_MODE)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("source-preparation asset write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
    except OSError as error:
        raise QuantizationAssetError(
            "failed to write owner-only source-preparation asset"
        ) from error
    finally:
        os.close(descriptor)


def _records_jsonl(records: Sequence[NormalizedCorpusRecord]) -> str:
    return "".join(
        json.dumps(
            item.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
        for item in records
    )


def _regular_file(path: Path, *, maximum_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise QuantizationAssetError(f"required regular file is missing: {path}")
    content = path.read_bytes()
    if len(content) > maximum_bytes:
        raise QuantizationAssetError(f"input exceeds its size limit: {path}")
    return content


def _parse_fixture_arguments(values: Sequence[str]) -> Mapping[MixCategory, Path]:
    result: dict[MixCategory, Path] = {}
    for value in values:
        category_value, separator, path_value = value.partition("=")
        if not separator:
            raise QuantizationAssetError("public fixtures use CATEGORY=/absolute/path.jsonl")
        try:
            category = MixCategory(category_value)
        except ValueError as error:
            raise QuantizationAssetError("public fixture category is unknown") from error
        if category not in _PUBLIC_CATEGORIES or category in result:
            raise QuantizationAssetError(
                "public fixtures require one unique approved public category"
            )
        result[category] = Path(path_value)
    return result


def _parse_attestation_arguments(values: Sequence[str]) -> Mapping[MixCategory, Path]:
    result: dict[MixCategory, Path] = {}
    for value in values:
        category_value, separator, path_value = value.partition("=")
        if not separator:
            raise QuantizationAssetError(
                "public attestations use CATEGORY=/absolute/path.attestation.json"
            )
        try:
            category = MixCategory(category_value)
        except ValueError as error:
            raise QuantizationAssetError("public attestation category is unknown") from error
        if category not in _PUBLIC_CATEGORIES or category in result:
            raise QuantizationAssetError(
                "public attestations require one unique approved public category"
            )
        result[category] = Path(path_value)
    return result


def validate_public_fixture_pairs(
    fixtures: Mapping[MixCategory, Path],
    attestations: Mapping[MixCategory, Path],
) -> None:
    if set(fixtures) != set(attestations):
        raise QuantizationAssetError(
            "every offline public fixture requires one matching Dataset Viewer attestation"
        )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source-registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="strict tracked source registry",
    )
    parser.add_argument(
        "--tokenizer-config",
        type=Path,
        required=True,
        help="revision-pinned tokenizer_config.json",
    )
    parser.add_argument(
        "--tokenizer-json",
        type=Path,
        required=True,
        help="tokenizer.json used by the attested runtime cross-check",
    )
    parser.add_argument(
        "--tokenizer-runtime-manifest",
        type=Path,
        required=True,
        help="attested tokenizer runtime identity JSON",
    )
    parser.add_argument(
        "--test-reference",
        type=Path,
        action="append",
        required=True,
        help="one exact sealed-Test JSONL; repeat exactly four times",
    )
    parser.add_argument(
        "--public-fixture",
        action="append",
        default=[],
        help="canonical offline CATEGORY=/path/rows.jsonl; requires matching attestation",
    )
    parser.add_argument(
        "--public-attestation",
        action="append",
        default=[],
        help="CATEGORY=/path/attestation.json captured from Dataset Viewer; repeat per fixture",
    )
    parser.add_argument(
        "--fetch-public",
        action="store_true",
        help="explicitly permit pinned Hugging Face Dataset Viewer network reads",
    )
    parser.add_argument(
        "--public-maximum-rows",
        type=int,
        default=50_000,
        help="maximum rows read from each public source",
    )
    parser.add_argument("--seed", default=DEFAULT_SEED, help="deterministic generator seed")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="new output directory; existing artifacts are never overwritten",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    if not 1 <= arguments.public_maximum_rows <= 50_000:
        raise QuantizationAssetError("public maximum rows must be between 1 and 50000")
    fixture_paths = _parse_fixture_arguments(arguments.public_fixture)
    attestation_paths = _parse_attestation_arguments(arguments.public_attestation)
    validate_public_fixture_pairs(fixture_paths, attestation_paths)
    registry = load_registry(arguments.source_registry)
    runtime_identity = load_runtime_identity(arguments.tokenizer_runtime_manifest)
    validate_tokenizer_config(arguments.tokenizer_config, registry)
    validate_local_source_revisions(registry)
    test_digests, leakage_index = load_test_references(arguments.test_reference)
    plan = build_corpus_plan(
        registry=registry,
        runtime_identity=runtime_identity,
        test_reference_digests=test_digests,
        seed=arguments.seed,
    )
    tokenizer = PinnedTokenizerJsonAdapter(
        tokenizer_json=arguments.tokenizer_json,
        identity_digest=runtime_identity.identity_digest,
    )
    synthetic = generate_csight_synthetic_sources(
        plan=plan,
        tokenizer=tokenizer,
        test_leakage_index=leakage_index,
    )
    pins = {item.category: item for item in plan.sources}
    fixtures = {
        category: load_attested_public_fixture(
            fixture_path=path,
            attestation_path=attestation_paths[category],
            source=pins[category],
            maximum_rows=arguments.public_maximum_rows,
        )
        for category, path in fixture_paths.items()
    }
    fetcher = HuggingFaceDatasetViewerRows() if arguments.fetch_public else None
    public = prepare_public_sources(
        plan=plan,
        tokenizer=tokenizer,
        test_leakage_index=leakage_index,
        fixtures=fixtures,
        fetcher=fetcher,
        maximum_rows=arguments.public_maximum_rows,
    )
    manifest = write_prepared_assets(
        output_dir=arguments.output_dir,
        plan=plan,
        synthetic=synthetic,
        public=public,
    )
    public_ready = manifest["public_categories_ready"]
    if not isinstance(public_ready, list):
        raise QuantizationAssetError("prepared manifest public readiness is invalid")
    status = "COMPLETE" if len(public_ready) == 2 else "CSIGHT_READY_PUBLIC_PENDING"
    print(
        "QWEN38_QUANTIZATION_SOURCES_PREPARED "
        f"status={status} plan={canonical_digest(plan)} output={arguments.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
