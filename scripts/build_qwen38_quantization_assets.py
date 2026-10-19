"""Build the frozen CSight Qwen3.8 calibration and isolated holdout corpora offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.platform.quantization_assets import (
    CorpusArtifact,
    CorpusBuild,
    CorpusSplit,
    MixCategory,
    NormalizedCorpusRecord,
    QuantizationAssetError,
    QuantizationCorpusManifestV1_1,
    QuantizationCorpusPlan,
    QuantizationSourcePreparationManifestV1_1,
    SourceKind,
    TestLeakageIndex,
    TokenizerPort,
    build_quantization_corpus,
    canonical_digest,
    serialize_source_preparation_manifest,
    string_leaves,
)
from app.platform.quantization_source_prep import (
    AttestedPublicDatasetRows,
    PublicDatasetFixtureAttestation,
    PublicDatasetRow,
    serialize_public_fixture,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / "local-data/qwen38-27b-quantization/corpus_plan.json"
DEFAULT_OUTPUT = ROOT / "local-data/qwen38-27b-quantization/corpus-v1.1"
MAX_PLAN_BYTES = 1024 * 1024
MAX_INPUT_BYTES = 512 * 1024 * 1024
MAX_TEST_BYTES = 32 * 1024 * 1024
MAX_SOURCE_PREPARATION_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_PUBLIC_ATTESTATION_BYTES = 4 * 1024 * 1024
MAX_PUBLIC_FIXTURE_BYTES = 512 * 1024 * 1024
_NORMALIZED_INPUT_NAMES = {
    "csight_synthetic_train.jsonl",
    "public_train.jsonl",
}
_PUBLIC_CATEGORIES = {
    MixCategory.PUBLIC_KO_WIKIPEDIA,
    MixCategory.PUBLIC_EN_WIKITEXT,
}


@dataclass(frozen=True)
class VerifiedSourcePreparation:
    manifest: QuantizationSourcePreparationManifestV1_1
    manifest_content_digest: str
    records: tuple[NormalizedCorpusRecord, ...]


class _TokenizerRuntimeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_version: str = Field(pattern=r"^tokenizer_runtime_identity/1\.0\.0$")
    identity_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    gguf_tokenizer_metadata_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    llama_cpp_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    implementation: str = Field(min_length=2, max_length=128)


class _PinnedTokenizer:
    def __init__(self, *, tokenizer_json: Path, identity_digest: str) -> None:
        try:
            from tokenizers import Tokenizer  # pyright: ignore[reportMissingImports]
        except ImportError as error:
            raise QuantizationAssetError(
                "tokenizers is required only for the explicit corpus-build command"
            ) from error
        self._tokenizer: Any = Tokenizer.from_file(str(tokenizer_json))
        self._identity_digest = identity_digest

    @property
    def identity_digest(self) -> str:
        return self._identity_digest

    def encode(self, text: str) -> tuple[int, ...]:
        return tuple(int(value) for value in self._tokenizer.encode(text).ids)

    def decode(self, token_ids: Sequence[int]) -> str:
        return str(self._tokenizer.decode(list(token_ids), skip_special_tokens=False))


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--test-reference", type=Path, action="append", required=True)
    parser.add_argument("--tokenizer-config", type=Path, required=True)
    parser.add_argument("--tokenizer-json", type=Path, required=True)
    parser.add_argument("--tokenizer-runtime-manifest", type=Path, required=True)
    parser.add_argument("--source-preparation-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _regular_file(path: Path, *, maximum_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise QuantizationAssetError(f"required regular file is missing: {path}")
    content = path.read_bytes()
    if len(content) > maximum_bytes:
        raise QuantizationAssetError(f"input exceeds its size limit: {path}")
    return content


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _load_plan(path: Path) -> tuple[QuantizationCorpusPlan, bytes]:
    payload = _regular_file(path, maximum_bytes=MAX_PLAN_BYTES)
    try:
        return QuantizationCorpusPlan.model_validate_json(payload), payload
    except ValidationError as error:
        raise QuantizationAssetError("corpus plan failed its strict schema") from error


def _parse_normalized_records(payloads: Mapping[str, bytes]) -> tuple[NormalizedCorpusRecord, ...]:
    records: list[NormalizedCorpusRecord] = []
    try:
        for content in payloads.values():
            records.extend(
                NormalizedCorpusRecord.model_validate_json(line)
                for line in content.splitlines()
                if line.strip()
            )
    except (UnicodeDecodeError, ValidationError) as error:
        raise QuantizationAssetError("normalized corpus input failed its strict schema") from error
    identities = tuple((item.source_id, item.record_id) for item in records)
    if len(identities) != len(set(identities)):
        raise QuantizationAssetError("normalized source record ids must be unique")
    return tuple(records)


def load_verified_source_preparation(
    *,
    manifest_path: Path,
    plan: QuantizationCorpusPlan,
    plan_payload: bytes,
    input_paths: Sequence[Path],
) -> VerifiedSourcePreparation:
    manifest_payload = _regular_file(
        manifest_path,
        maximum_bytes=MAX_SOURCE_PREPARATION_MANIFEST_BYTES,
    )
    try:
        manifest = QuantizationSourcePreparationManifestV1_1.model_validate_json(manifest_payload)
    except ValidationError as error:
        raise QuantizationAssetError(
            "source-preparation manifest must be strict attested v1.1 evidence"
        ) from error
    if manifest_payload != serialize_source_preparation_manifest(manifest):
        raise QuantizationAssetError(
            "source-preparation manifest bytes are not canonical v1.1 JSON"
        )
    expected_plan_digest = canonical_digest(plan)
    if manifest.plan_digest != expected_plan_digest:
        raise QuantizationAssetError("source-preparation plan digest does not match the build plan")
    if manifest.files["corpus_plan.json"] != _sha256(plan_payload):
        raise QuantizationAssetError(
            "source-preparation plan file digest does not match the exact build input"
        )

    if len(input_paths) != len(_NORMALIZED_INPUT_NAMES):
        raise QuantizationAssetError(
            "corpus build requires the exact synthetic and public normalized inputs"
        )
    paths_by_name = {path.name: path for path in input_paths}
    if set(paths_by_name) != _NORMALIZED_INPUT_NAMES or len(paths_by_name) != len(input_paths):
        raise QuantizationAssetError(
            "normalized inputs must be csight_synthetic_train.jsonl and public_train.jsonl"
        )
    normalized_payloads: dict[str, bytes] = {}
    for name in sorted(_NORMALIZED_INPUT_NAMES):
        payload = _regular_file(paths_by_name[name], maximum_bytes=MAX_INPUT_BYTES)
        if _sha256(payload) != manifest.files[name]:
            raise QuantizationAssetError(
                f"normalized input digest does not match source preparation: {name}"
            )
        normalized_payloads[name] = payload
    records = _parse_normalized_records(normalized_payloads)
    _validate_normalized_source_evidence(
        plan=plan,
        manifest=manifest,
        normalized_payloads=normalized_payloads,
        records=records,
    )
    _validate_public_capture_evidence(
        manifest_path=manifest_path,
        manifest=manifest,
        plan=plan,
    )
    return VerifiedSourcePreparation(
        manifest=manifest,
        manifest_content_digest=_sha256(manifest_payload),
        records=records,
    )


def _validate_normalized_source_evidence(
    *,
    plan: QuantizationCorpusPlan,
    manifest: QuantizationSourcePreparationManifestV1_1,
    normalized_payloads: Mapping[str, bytes],
    records: Sequence[NormalizedCorpusRecord],
) -> None:
    records_by_file = {
        name: _parse_normalized_records({name: payload})
        for name, payload in normalized_payloads.items()
    }
    synthetic = records_by_file["csight_synthetic_train.jsonl"]
    public = records_by_file["public_train.jsonl"]
    if not synthetic or not public:
        raise QuantizationAssetError(
            "both synthetic and public normalized inputs must be non-empty"
        )
    if any(
        item.category in _PUBLIC_CATEGORIES or item.source_partition != "SYNTHETIC_TRAIN"
        for item in synthetic
    ):
        raise QuantizationAssetError("synthetic normalized input contains a public source record")
    if any(
        item.category not in _PUBLIC_CATEGORIES or item.source_partition != "PUBLIC_TRAIN"
        for item in public
    ):
        raise QuantizationAssetError("public normalized input contains a synthetic source record")
    counts = {category: 0 for category in MixCategory}
    for item in records:
        counts[item.category] += 1
    stats = {item.category: item for item in manifest.stats}
    for category in MixCategory:
        expected_tokens = sum(plan.target_for(split, category) for split in CorpusSplit)
        stat = stats[category]
        if stat.record_count != counts[category]:
            raise QuantizationAssetError(
                f"source-preparation record count does not match normalized input: {category.value}"
            )
        if stat.required_token_count != expected_tokens:
            raise QuantizationAssetError(
                f"source-preparation token target does not match the build plan: {category.value}"
            )
        if stat.screened_token_count < stat.required_token_count:
            raise QuantizationAssetError(
                f"source-preparation screened tokens are insufficient: {category.value}"
            )


def _validate_public_capture_evidence(
    *,
    manifest_path: Path,
    manifest: QuantizationSourcePreparationManifestV1_1,
    plan: QuantizationCorpusPlan,
) -> None:
    bundle_root = manifest_path.parent.resolve()
    pins = {
        item.category: item for item in plan.sources if item.kind is SourceKind.HUGGING_FACE_DATASET
    }
    if set(pins) != _PUBLIC_CATEGORIES:
        raise QuantizationAssetError(
            "build plan must pin both approved public Dataset Viewer sources"
        )
    for evidence in manifest.public_source_attestations:
        fixture_payload = _read_bundle_file(
            bundle_root=bundle_root,
            relative_path=evidence.fixture_path,
            maximum_bytes=MAX_PUBLIC_FIXTURE_BYTES,
        )
        attestation_payload = _read_bundle_file(
            bundle_root=bundle_root,
            relative_path=evidence.attestation_path,
            maximum_bytes=MAX_PUBLIC_ATTESTATION_BYTES,
        )
        if _sha256(fixture_payload) != evidence.fixture_digest:
            raise QuantizationAssetError("public fixture digest does not match source preparation")
        if _sha256(attestation_payload) != evidence.attestation_digest:
            raise QuantizationAssetError(
                "public attestation digest does not match source preparation"
            )
        try:
            attestation = PublicDatasetFixtureAttestation.model_validate_json(attestation_payload)
        except ValidationError as error:
            raise QuantizationAssetError(
                "public Dataset Viewer attestation failed strict validation"
            ) from error
        rows = _parse_public_fixture(fixture_payload)
        try:
            AttestedPublicDatasetRows(rows=rows, attestation=attestation)
        except ValidationError as error:
            raise QuantizationAssetError(
                "public fixture does not match its Dataset Viewer attestation"
            ) from error
        pin = pins[evidence.category]
        if (
            evidence.source_id,
            evidence.source_revision,
            evidence.query_identity_digest,
        ) != (
            attestation.source_id,
            attestation.source_revision,
            attestation.query_identity_digest,
        ):
            raise QuantizationAssetError(
                "public source-preparation evidence does not match its attestation"
            )
        if (
            attestation.source_id,
            attestation.source_revision,
            attestation.config,
            attestation.split,
        ) != (pin.source_id, pin.revision, pin.config, pin.split):
            raise QuantizationAssetError(
                "public Dataset Viewer attestation does not match the exact build-plan pin"
            )


def _read_bundle_file(*, bundle_root: Path, relative_path: str, maximum_bytes: int) -> bytes:
    candidate = bundle_root / relative_path
    try:
        candidate.resolve().relative_to(bundle_root)
    except ValueError as error:
        raise QuantizationAssetError("source-preparation evidence escapes its bundle") from error
    return _regular_file(candidate, maximum_bytes=maximum_bytes)


def _parse_public_fixture(payload: bytes) -> tuple[PublicDatasetRow, ...]:
    rows: list[PublicDatasetRow] = []
    for line in payload.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise QuantizationAssetError("public fixture contains invalid JSONL") from error
        if not isinstance(value, Mapping) or set(value) != {"row", "row_idx"}:
            raise QuantizationAssetError("public fixture must use canonical Dataset Viewer rows")
        row_index = value.get("row_idx")
        row_values = value.get("row")
        if not isinstance(row_index, int) or row_index < 0 or not isinstance(row_values, Mapping):
            raise QuantizationAssetError("public fixture row payload is invalid")
        rows.append(PublicDatasetRow(row_index=row_index, values=dict(row_values)))
    canonical_payload = serialize_public_fixture(rows)
    if canonical_payload != payload:
        raise QuantizationAssetError("public fixture bytes are not canonical JSONL")
    return tuple(rows)


def _load_test_index(paths: list[Path], expected_digests: tuple[str, ...]) -> TestLeakageIndex:
    payloads = tuple(_regular_file(path, maximum_bytes=MAX_TEST_BYTES) for path in paths)
    digests = tuple(_sha256(value) for value in payloads)
    if set(digests) != set(expected_digests):
        raise QuantizationAssetError("Test reference digests do not match the frozen plan")
    leaves: list[str] = []
    for payload in payloads:
        for line in payload.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("split") == "test":
                leaves.extend(string_leaves(row))
    return TestLeakageIndex(leaves)


def _validate_tokenizer_contract(
    *,
    plan: QuantizationCorpusPlan,
    tokenizer_config_path: Path,
    runtime_manifest_path: Path,
) -> _TokenizerRuntimeManifest:
    tokenizer_config_bytes = _regular_file(tokenizer_config_path, maximum_bytes=32 * 1024 * 1024)
    if _sha256(tokenizer_config_bytes) != plan.chat_template.tokenizer_config_digest:
        raise QuantizationAssetError("tokenizer_config digest does not match the frozen plan")
    config = json.loads(tokenizer_config_bytes)
    template = config.get("chat_template")
    if not isinstance(template, str):
        raise QuantizationAssetError("tokenizer_config does not contain a string chat_template")
    if _sha256(template.encode()) != plan.chat_template.chat_template_digest:
        raise QuantizationAssetError("chat_template digest does not match the frozen plan")
    try:
        runtime = _TokenizerRuntimeManifest.model_validate_json(
            _regular_file(runtime_manifest_path, maximum_bytes=1024 * 1024)
        )
    except ValidationError as error:
        raise QuantizationAssetError(
            "tokenizer runtime manifest failed its strict schema"
        ) from error
    expected = plan.chat_template
    if (
        runtime.identity_digest != expected.tokenizer_runtime_identity_digest
        or runtime.gguf_tokenizer_metadata_digest != expected.gguf_tokenizer_metadata_digest
        or runtime.llama_cpp_revision != expected.llama_cpp_revision
        or runtime.implementation != expected.tokenizer_implementation
    ):
        raise QuantizationAssetError("tokenizer runtime identity does not match the frozen plan")
    return runtime


def write_quantization_corpus_v1_1(
    *,
    output_dir: Path,
    plan: QuantizationCorpusPlan,
    build: CorpusBuild,
    tokenizer: TokenizerPort,
    source_preparation: VerifiedSourcePreparation,
) -> QuantizationCorpusManifestV1_1:
    if output_dir.is_symlink():
        raise QuantizationAssetError("output directory must not be a symlink")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    output_paths = [manifest_path]
    for split in CorpusSplit:
        output_paths.extend(
            (
                output_dir / f"{split.value.casefold()}.txt",
                output_dir / f"{split.value.casefold()}_index.jsonl",
            )
        )
    if any(path.exists() or path.is_symlink() for path in output_paths):
        raise QuantizationAssetError("refusing to overwrite existing corpus-v1.1 artifacts")
    artifacts: list[CorpusArtifact] = []
    for split in CorpusSplit:
        samples = build.samples_for(split)
        text = "".join(item.text for item in samples)
        actual_tokens = len(tokenizer.encode(text))
        expected_tokens = sum(item.token_count for item in samples)
        if actual_tokens != expected_tokens:
            raise QuantizationAssetError(
                f"concatenated {split.value} corpus changed token boundaries"
            )
        relative = f"{split.value.casefold()}.txt"
        target = output_dir / relative
        if target.exists() or target.is_symlink():
            raise QuantizationAssetError(f"refusing to overwrite corpus artifact: {target}")
        target.write_text(text, encoding="utf-8")
        artifacts.append(
            CorpusArtifact(
                split=split,
                relative_path=relative,
                content_digest=_sha256(target.read_bytes()),
                token_count=actual_tokens,
                record_count=len(samples),
            )
        )
        index_path = output_dir / f"{split.value.casefold()}_index.jsonl"
        index_path.write_text(
            "".join(
                json.dumps(
                    item.model_dump(mode="json", exclude={"text"}),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
                for item in samples
            ),
            encoding="utf-8",
        )
    manifest = QuantizationCorpusManifestV1_1(
        plan_digest=canonical_digest(plan),
        tokenizer_identity_digest=tokenizer.identity_digest,
        chat_template=plan.chat_template,
        source_pins=plan.sources,
        mix=plan.mix,
        artifacts=tuple(artifacts),
        safety=build.safety,
        source_preparation_manifest_digest=(source_preparation.manifest_content_digest),
        source_preparation=source_preparation.manifest,
    )
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    arguments = _arguments()
    plan, plan_payload = _load_plan(arguments.plan)
    source_preparation = load_verified_source_preparation(
        manifest_path=arguments.source_preparation_manifest,
        plan=plan,
        plan_payload=plan_payload,
        input_paths=arguments.input,
    )
    runtime = _validate_tokenizer_contract(
        plan=plan,
        tokenizer_config_path=arguments.tokenizer_config,
        runtime_manifest_path=arguments.tokenizer_runtime_manifest,
    )
    tokenizer = _PinnedTokenizer(
        tokenizer_json=arguments.tokenizer_json,
        identity_digest=runtime.identity_digest,
    )
    build = build_quantization_corpus(
        plan=plan,
        records=source_preparation.records,
        tokenizer=tokenizer,
        test_leakage_index=_load_test_index(arguments.test_reference, plan.test_reference_digests),
    )
    manifest = write_quantization_corpus_v1_1(
        output_dir=arguments.output_dir,
        plan=plan,
        build=build,
        tokenizer=tokenizer,
        source_preparation=source_preparation,
    )
    print(
        "QWEN38_QUANTIZATION_CORPUS_BUILT "
        f"calibration=750000 ppl_holdout=100000 logits_holdout=16000 "
        f"manifest={canonical_digest(manifest)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
