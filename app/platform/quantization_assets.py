"""Framework-free contracts for reproducible, PII-free GGUF quantization assets."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from enum import StrEnum
    from typing import Self
else:
    try:
        from enum import StrEnum
    except ImportError:  # pragma: no cover - isolated Python 3.10 maintenance host
        from enum import Enum

        class StrEnum(str, Enum):  # noqa: UP042
            """Python 3.10 compatibility for the isolated quantization runner."""

            def __str__(self) -> str:
                return self.value

    try:
        from typing import Self
    except ImportError:  # pragma: no cover - isolated Python 3.10 maintenance host
        from typing_extensions import Self  # noqa: UP035

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_REVISION_PATTERN = r"^[0-9a-f]{40}$"
LLAMA_CPP_B10419_REVISION = "aee56b3abfeb134218fe5c496c329a1faac1ef28"
LLAMA_CPP_B10419_BUILD = "b10419"
LLAMA_CPP_IMATRIX_OUTPUT_FREQUENCY = 1_000_000
_EXPECTED_MIX = (35, 20, 10, 10, 20, 5)
_SPLIT_TOKEN_TARGETS = {
    "CALIBRATION": 750_000,
    "PPL_HOLDOUT": 100_000,
    "LOGITS_HOLDOUT": 16_000,
}


class QuantizationAssetError(ValueError):
    """A quantization input cannot produce auditable or isolated evidence."""


class MixCategory(StrEnum):
    CSIGHT_EXTRACTION = "CSIGHT_EXTRACTION"
    CSIGHT_POLICY_GROUNDING = "CSIGHT_POLICY_GROUNDING"
    CSIGHT_QUERY_BUILDER = "CSIGHT_QUERY_BUILDER"
    CSIGHT_SAFETY_JSON_INJECTION = "CSIGHT_SAFETY_JSON_INJECTION"
    PUBLIC_KO_WIKIPEDIA = "PUBLIC_KO_WIKIPEDIA"
    PUBLIC_EN_WIKITEXT = "PUBLIC_EN_WIKITEXT"


class CorpusSplit(StrEnum):
    CALIBRATION = "CALIBRATION"
    PPL_HOLDOUT = "PPL_HOLDOUT"
    LOGITS_HOLDOUT = "LOGITS_HOLDOUT"


class SourceKind(StrEnum):
    HUGGING_FACE_DATASET = "HUGGING_FACE_DATASET"
    LOCAL_SYNTHETIC = "LOCAL_SYNTHETIC"


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class MixQuota(_Contract):
    category: MixCategory
    percent: int = Field(gt=0, le=100)


class SourcePin(_Contract):
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")
    kind: SourceKind
    category: MixCategory
    revision: str
    license_identifier: str = Field(min_length=2, max_length=128)
    visibility: Literal["PUBLIC", "LOCAL_SYNTHETIC"]
    config: str | None = Field(default=None, max_length=128)
    split: str | None = Field(default=None, max_length=128)
    pii_usage: Literal["PUBLIC_LICENSED_PII_SCREENED", "SYNTHETIC_PII_FREE"]

    @model_validator(mode="after")
    def require_immutable_revision(self) -> Self:
        if self.kind is SourceKind.HUGGING_FACE_DATASET:
            if re.fullmatch(_REVISION_PATTERN, self.revision) is None:
                raise ValueError("Hugging Face sources require an exact 40-character revision")
            if self.config is None or self.split is None:
                raise ValueError("Hugging Face sources require config and split")
            if self.visibility != "PUBLIC":
                raise ValueError("private Hub sources are SHADOW-only, not calibration inputs")
        elif re.fullmatch(_DIGEST_PATTERN, self.revision) is None:
            raise ValueError("local sources require an exact sha256 content revision")
        elif self.visibility != "LOCAL_SYNTHETIC":
            raise ValueError("local calibration sources must be synthetic")
        return self


class ChatTemplateContract(_Contract):
    model_artifact: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    model_revision: str = Field(pattern=_REVISION_PATTERN)
    tokenizer_config_digest: str = Field(pattern=_DIGEST_PATTERN)
    chat_template_digest: str = Field(pattern=_DIGEST_PATTERN)
    gguf_tokenizer_metadata_digest: str = Field(pattern=_DIGEST_PATTERN)
    llama_cpp_revision: str = Field(pattern=_REVISION_PATTERN)
    tokenizer_implementation: str = Field(min_length=2, max_length=128)
    tokenizer_runtime_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    enable_thinking: Literal[False] = False
    preserve_thinking: Literal[False] = False
    tools_enabled: Literal[False] = False
    add_generation_prompt: Literal[False] = False
    renderer: Literal["qwen3.8-text-only-nonthinking/1.0.0"] = "qwen3.8-text-only-nonthinking/1.0.0"


class QuantizationCorpusPlan(_Contract):
    schema_version: Literal["quantization_corpus_plan/1.0.0"] = "quantization_corpus_plan/1.0.0"
    plan_name: str = Field(min_length=3, max_length=128)
    seed: str = Field(min_length=8, max_length=128, repr=False)
    calibration_tokens: Literal[750000] = 750_000
    ppl_holdout_tokens: Literal[100000] = 100_000
    logits_holdout_tokens: Literal[16000] = 16_000
    mix: tuple[MixQuota, ...] = Field(min_length=6, max_length=6)
    chat_template: ChatTemplateContract
    sources: tuple[SourcePin, ...] = Field(min_length=6)
    test_reference_digests: tuple[str, ...] = Field(min_length=3)

    @field_validator("test_reference_digests")
    @classmethod
    def require_test_digests(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(re.fullmatch(_DIGEST_PATTERN, value) is None for value in values):
            raise ValueError("test reference digests must be sha256 values")
        if len(values) != len(set(values)):
            raise ValueError("test reference digests must be unique")
        return values

    @model_validator(mode="after")
    def require_frozen_mix_and_sources(self) -> Self:
        categories = tuple(item.category for item in self.mix)
        if categories != tuple(MixCategory):
            raise ValueError("mix categories must use the canonical order")
        if tuple(item.percent for item in self.mix) != _EXPECTED_MIX:
            raise ValueError("the frozen mix must be exactly 35/20/10/10/20/5")
        source_categories = {item.category for item in self.sources}
        if source_categories != set(MixCategory):
            raise ValueError("every mix category requires at least one pinned source")
        source_ids = tuple(item.source_id for item in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source ids must be unique")
        return self

    def target_for(self, split: CorpusSplit, category: MixCategory) -> int:
        total = _SPLIT_TOKEN_TARGETS[split.value]
        percent = next(item.percent for item in self.mix if item.category is category)
        return total * percent // 100


class ChatMessage(_Contract):
    role: ChatRole
    content: str = Field(min_length=1, max_length=200_000, repr=False)


class NormalizedCorpusRecord(_Contract):
    schema_version: Literal["normalized_quant_record/1.0.0"] = "normalized_quant_record/1.0.0"
    record_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,255}$")
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")
    source_revision: str
    category: MixCategory
    license_identifier: str = Field(min_length=2, max_length=128)
    pii_reviewed: Literal[True]
    source_partition: Literal["DEV", "PUBLIC_TRAIN", "SYNTHETIC_TRAIN"]
    messages: tuple[ChatMessage, ...] = Field(min_length=1, max_length=64, repr=False)

    @model_validator(mode="after")
    def require_safe_conversation_shape(self) -> Self:
        roles = tuple(item.role for item in self.messages)
        if roles.count(ChatRole.SYSTEM) > 1:
            raise ValueError("at most one system message is allowed")
        if ChatRole.SYSTEM in roles and roles[0] is not ChatRole.SYSTEM:
            raise ValueError("the system message must be first")
        if ChatRole.USER not in roles:
            raise ValueError("a corpus conversation requires a user message")
        return self


class TokenizerPort(Protocol):
    """Exact pinned tokenizer boundary; implementations may use llama.cpp or tokenizers."""

    @property
    def identity_digest(self) -> str: ...

    def encode(self, text: str) -> tuple[int, ...]: ...

    def decode(self, token_ids: Sequence[int]) -> str: ...


class PreparedCorpusSample(_Contract):
    # Corpus bytes are token-counted before validation.  The rendered chat delimiter
    # intentionally ends in ``\n``; stripping it here changes the pinned token count.
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    record_id_hash: str = Field(pattern=_DIGEST_PATTERN)
    source_id: str
    source_revision: str
    category: MixCategory
    split: CorpusSplit
    token_count: int = Field(gt=0)
    content_digest: str = Field(pattern=_DIGEST_PATTERN)
    text: str = Field(min_length=1, repr=False)
    truncated: bool = False


class CorpusSafetyReport(_Contract):
    input_records: int = Field(ge=0)
    accepted_records: int = Field(ge=0)
    duplicate_rejections: int = Field(ge=0)
    pii_rejections: int = Field(ge=0)
    test_overlap_rejections: int = Field(ge=0)
    source_contract_rejections: int = Field(ge=0)
    split_overlap_count: Literal[0] = 0
    output_pii_findings: Literal[0] = 0
    output_test_overlap_findings: Literal[0] = 0


class CorpusBuild(_Contract):
    samples: tuple[PreparedCorpusSample, ...] = Field(repr=False)
    safety: CorpusSafetyReport

    def samples_for(self, split: CorpusSplit) -> tuple[PreparedCorpusSample, ...]:
        return tuple(item for item in self.samples if item.split is split)


class CorpusArtifact(_Contract):
    split: CorpusSplit
    relative_path: str = Field(pattern=r"^[A-Za-z0-9._/-]+$")
    content_digest: str = Field(pattern=_DIGEST_PATTERN)
    token_count: int = Field(gt=0)
    record_count: int = Field(gt=0)


class SourcePreparationStats(_Contract):
    category: MixCategory
    record_count: int = Field(gt=0)
    screened_token_count: int = Field(gt=0)
    required_token_count: int = Field(gt=0)
    source_partition: Literal["SYNTHETIC_TRAIN", "PUBLIC_TRAIN"]


class PublicSourceAttestationEvidence(_Contract):
    attestation_digest: str = Field(pattern=_DIGEST_PATTERN)
    attestation_path: str = Field(pattern=r"^[A-Za-z0-9._/-]+$")
    category: Literal[
        MixCategory.PUBLIC_KO_WIKIPEDIA,
        MixCategory.PUBLIC_EN_WIKITEXT,
    ]
    fixture_digest: str = Field(pattern=_DIGEST_PATTERN)
    fixture_path: str = Field(pattern=r"^[A-Za-z0-9._/-]+$")
    query_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{2,255}$")
    source_revision: str = Field(pattern=_REVISION_PATTERN)

    @field_validator("attestation_path", "fixture_path")
    @classmethod
    def require_safe_relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("source-attestation paths must be safe relative paths")
        return value


class QuantizationSourcePreparationManifestV1_1(_Contract):
    """Strict source-preparation evidence required by a qualified corpus build."""

    schema_version: Literal["quantization_source_preparation_manifest/1.1.0"] = (
        "quantization_source_preparation_manifest/1.1.0"
    )
    plan_digest: str = Field(pattern=_DIGEST_PATTERN)
    generator_version: Literal["csight-qwen38-source-generator/1.0.0"] = (
        "csight-qwen38-source-generator/1.0.0"
    )
    files: dict[str, str]
    stats: tuple[SourcePreparationStats, ...] = Field(min_length=6, max_length=6)
    public_categories_ready: tuple[
        Literal[
            MixCategory.PUBLIC_KO_WIKIPEDIA,
            MixCategory.PUBLIC_EN_WIKITEXT,
        ],
        ...,
    ] = Field(min_length=2, max_length=2)
    public_source_attestations: tuple[PublicSourceAttestationEvidence, ...] = Field(
        min_length=2,
        max_length=2,
    )
    public_source_capture_scope: Literal["LOCAL_PROVENANCE_ONLY_NOT_MODEL_ARTIFACT"] = (
        "LOCAL_PROVENANCE_ONLY_NOT_MODEL_ARTIFACT"
    )
    public_source_captures_pii_screened: Literal[False] = False
    normalized_outputs_pii_screened: Literal[True] = True
    raw_customer_data_used: Literal[False] = False
    direct_identifiers_present: Literal[False] = False
    sealed_test_records_used: Literal[False] = False
    model_calls_performed: Literal[0] = 0

    @field_validator("files")
    @classmethod
    def require_exact_file_set(cls, value: dict[str, str]) -> dict[str, str]:
        expected = {
            "corpus_plan.json",
            "csight_synthetic_train.jsonl",
            "public_train.jsonl",
        }
        if set(value) != expected:
            raise ValueError("source-preparation files must be the exact normalized input set")
        if any(re.fullmatch(_DIGEST_PATTERN, digest) is None for digest in value.values()):
            raise ValueError("source-preparation files require SHA-256 digests")
        return value

    @model_validator(mode="after")
    def require_complete_public_and_safety_evidence(self) -> Self:
        expected_public = {
            MixCategory.PUBLIC_KO_WIKIPEDIA,
            MixCategory.PUBLIC_EN_WIKITEXT,
        }
        stat_categories = tuple(item.category for item in self.stats)
        if stat_categories != tuple(MixCategory):
            raise ValueError(
                "source-preparation stats must cover each mix category in canonical order"
            )
        for item in self.stats:
            expected_partition = (
                "PUBLIC_TRAIN" if item.category in expected_public else "SYNTHETIC_TRAIN"
            )
            if item.source_partition != expected_partition:
                raise ValueError("source-preparation stats use the wrong source partition")
        categories = tuple(self.public_categories_ready)
        attested_categories = tuple(item.category for item in self.public_source_attestations)
        if (
            len(categories) != len(set(categories))
            or set(categories) != expected_public
            or len(attested_categories) != len(set(attested_categories))
            or set(attested_categories) != expected_public
        ):
            raise ValueError("both approved public categories require one attestation")
        if tuple(sorted(item.value for item in categories)) != tuple(
            item.value for item in categories
        ):
            raise ValueError("public categories must use deterministic sorted order")
        if tuple(sorted(item.category.value for item in self.public_source_attestations)) != tuple(
            item.category.value for item in self.public_source_attestations
        ):
            raise ValueError("public attestations must use deterministic sorted order")
        paths = tuple(
            path
            for item in self.public_source_attestations
            for path in (item.fixture_path, item.attestation_path)
        )
        if len(paths) != len(set(paths)):
            raise ValueError("public fixture and attestation paths must be unique")
        return self


class QuantizationCorpusManifest(_Contract):
    """Legacy R&D corpus manifest retained for read compatibility only."""

    schema_version: Literal["quantization_corpus_manifest/1.0.0"] = (
        "quantization_corpus_manifest/1.0.0"
    )
    plan_digest: str = Field(pattern=_DIGEST_PATTERN)
    tokenizer_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    chat_template: ChatTemplateContract
    source_pins: tuple[SourcePin, ...]
    mix: tuple[MixQuota, ...]
    artifacts: tuple[CorpusArtifact, ...] = Field(min_length=3, max_length=3)
    safety: CorpusSafetyReport
    raw_customer_text_in_manifest: Literal[False] = False
    direct_identifiers_in_manifest: Literal[False] = False


def serialize_source_preparation_manifest(
    manifest: QuantizationSourcePreparationManifestV1_1,
) -> bytes:
    """Render the one canonical byte form whose digest is carried into corpus v1.1."""

    return (
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


class QuantizationCorpusManifestV1_1(_Contract):
    """Corpus manifest cryptographically bound to attested source preparation."""

    schema_version: Literal["quantization_corpus_manifest/1.1.0"] = (
        "quantization_corpus_manifest/1.1.0"
    )
    plan_digest: str = Field(pattern=_DIGEST_PATTERN)
    tokenizer_identity_digest: str = Field(pattern=_DIGEST_PATTERN)
    chat_template: ChatTemplateContract
    source_pins: tuple[SourcePin, ...]
    mix: tuple[MixQuota, ...]
    artifacts: tuple[CorpusArtifact, ...] = Field(min_length=3, max_length=3)
    safety: CorpusSafetyReport
    source_preparation_manifest_digest: str = Field(pattern=_DIGEST_PATTERN)
    source_preparation: QuantizationSourcePreparationManifestV1_1
    raw_customer_text_in_manifest: Literal[False] = False
    direct_identifiers_in_manifest: Literal[False] = False

    @model_validator(mode="after")
    def require_source_preparation_binding(self) -> Self:
        expected_manifest_digest = (
            "sha256:"
            + hashlib.sha256(
                serialize_source_preparation_manifest(self.source_preparation)
            ).hexdigest()
        )
        if self.source_preparation_manifest_digest != expected_manifest_digest:
            raise ValueError("source-preparation manifest digest does not match its exact content")
        if self.source_preparation.plan_digest != self.plan_digest:
            raise ValueError("corpus and source-preparation plan digests must match")
        public_pins = tuple(
            item
            for item in self.source_pins
            if item.category
            in {
                MixCategory.PUBLIC_KO_WIKIPEDIA,
                MixCategory.PUBLIC_EN_WIKITEXT,
            }
        )
        pins = {item.category: item for item in public_pins}
        if len(public_pins) != 2 or set(pins) != {
            MixCategory.PUBLIC_KO_WIKIPEDIA,
            MixCategory.PUBLIC_EN_WIKITEXT,
        }:
            raise ValueError("corpus manifest requires both approved public source pins")
        for evidence in self.source_preparation.public_source_attestations:
            pin = pins[evidence.category]
            if (evidence.source_id, evidence.source_revision) != (
                pin.source_id,
                pin.revision,
            ):
                raise ValueError("public attestation evidence does not match the corpus source pin")
        return self


QuantizationCorpusManifestAny = QuantizationCorpusManifest | QuantizationCorpusManifestV1_1


class TensorInfo(_Contract):
    name: str = Field(min_length=1, max_length=512)
    shape: tuple[int, ...] = Field(min_length=1, max_length=8)
    dtype: str = Field(min_length=1, max_length=64)
    n_bytes: int = Field(gt=0)

    @field_validator("shape")
    @classmethod
    def require_positive_shape(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(item <= 0 for item in value):
            raise ValueError("tensor dimensions must be positive")
        return value


class TensorInventory(_Contract):
    schema_version: Literal["gguf_tensor_inventory/1.0.0"] = "gguf_tensor_inventory/1.0.0"
    source_gguf_digest: str = Field(pattern=_DIGEST_PATTERN)
    tensors: tuple[TensorInfo, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_qwen_inventory(self) -> Self:
        names = tuple(item.name for item in self.tensors)
        if len(names) != len(set(names)):
            raise ValueError("tensor names must be unique")
        required_global = {"token_embd.weight", "output_norm.weight", "output.weight"}
        if not required_global <= set(names):
            raise ValueError("inventory is missing required embedding/output tensors")
        block_ids = sorted(
            {
                int(match.group(1))
                for name in names
                if (match := re.match(r"^blk\.(\d+)\.", name)) is not None
            }
        )
        if block_ids != list(range(64)):
            raise ValueError("Qwen3.8-27B inventory must contain exactly 64 contiguous blocks")
        feed_forward_suffixes = ("ffn_gate.weight", "ffn_up.weight", "ffn_down.weight")
        full_attention_suffixes = (
            "attn_q.weight",
            "attn_k.weight",
            "attn_v.weight",
            "attn_output.weight",
        )
        linear_attention_suffixes = (
            "attn_qkv.weight",
            "attn_gate.weight",
            "ssm_out.weight",
        )
        names_set = set(names)
        missing = [
            f"blk.{block}.{suffix}"
            for block in block_ids
            for suffix in feed_forward_suffixes
            if f"blk.{block}.{suffix}" not in names_set
        ]
        if missing:
            raise ValueError(f"inventory is missing required block tensors: {missing[0]}")
        expected_full_attention = set(range(3, 64, 4))
        observed_full_attention: set[int] = set()
        observed_linear_attention: set[int] = set()
        for block in block_ids:
            full_present = {
                suffix for suffix in full_attention_suffixes if f"blk.{block}.{suffix}" in names_set
            }
            linear_present = {
                suffix
                for suffix in linear_attention_suffixes
                if f"blk.{block}.{suffix}" in names_set
            }
            if full_present == set(full_attention_suffixes) and not linear_present:
                observed_full_attention.add(block)
            elif linear_present == set(linear_attention_suffixes) and not full_present:
                observed_linear_attention.add(block)
            else:
                raise ValueError(
                    f"block {block} does not match one complete Qwen3.8 attention family"
                )
        if observed_full_attention != expected_full_attention:
            raise ValueError("Qwen3.8-27B must contain 16 full-attention blocks at interval four")
        if observed_linear_attention != set(block_ids) - expected_full_attention:
            raise ValueError("Qwen3.8-27B must contain 48 linear-attention blocks")
        return self

    @property
    def block_count(self) -> int:
        return (
            max(
                int(match.group(1))
                for item in self.tensors
                if (match := re.match(r"^blk\.(\d+)\.", item.name)) is not None
            )
            + 1
        )


class QuantizationRecipeName(StrEnum):
    Q4_K_M_CONTROL = "Q4_K_M_CONTROL"
    Q4_K_M_IMATRIX = "Q4_K_M_IMATRIX"
    Q4_K_M_CSIGHT_MIXED = "Q4_K_M_CSIGHT_MIXED"
    Q5_K_S_IMATRIX = "Q5_K_S_IMATRIX"


class FinalCandidateSet(StrEnum):
    """Exact output set admitted by a pinned final-candidate run plan."""

    FOUR_WAY_COMPARISON = "FOUR_WAY_COMPARISON"
    DEV_QUALIFICATION_PAIR = "DEV_QUALIFICATION_PAIR"


class TensorQuantization(_Contract):
    tensor_name: str
    target_type: str = Field(pattern=r"^(Q5_K|Q6_K|F32)$")
    rationale: str = Field(min_length=3, max_length=255)


class CalibrationHelperRecipe(_Contract):
    schema_version: Literal["gguf_calibration_helper_recipe/1.0.0"] = (
        "gguf_calibration_helper_recipe/1.0.0"
    )
    source_bf16_gguf_digest: str = Field(pattern=_DIGEST_PATTERN)
    tensor_inventory_digest: str = Field(pattern=_DIGEST_PATTERN)
    helper_type: Literal["Q8_0"] = "Q8_0"
    llama_cpp_revision: str = Field(pattern=_REVISION_PATTERN)
    helper_purpose: Literal["IMATRIX_COMPUTE_ONLY"] = "IMATRIX_COMPUTE_ONLY"
    final_quantization_source: Literal["BF16_GGUF"] = "BF16_GGUF"
    allow_output_overwrite: Literal[False] = False
    recipe_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def require_canonical_recipe_digest(self) -> Self:
        if self.recipe_digest != canonical_digest(self):
            raise ValueError("calibration-helper recipe digest does not match its content")
        return self


class CompiledQuantizationRecipe(_Contract):
    schema_version: Literal["gguf_quantization_recipe/1.0.0"] = "gguf_quantization_recipe/1.0.0"
    recipe_name: QuantizationRecipeName
    source_gguf_digest: str = Field(pattern=_DIGEST_PATTERN)
    tensor_inventory_digest: str = Field(pattern=_DIGEST_PATTERN)
    calibration_manifest_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    imatrix_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    calibration_helper_q8_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    default_type: Literal["Q4_K_M", "Q5_K_S"]
    overrides: tuple[TensorQuantization, ...]
    llama_cpp_revision: str = Field(pattern=_REVISION_PATTERN)
    quantization_source: Literal["BF16_GGUF"] = "BF16_GGUF"
    imatrix_compute_source: Literal["NONE", "Q8_0_HELPER"]
    allow_output_overwrite: Literal[False] = False
    test_data_used_for_quantization: Literal[False] = False
    recipe_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def require_canonical_recipe_digest(self) -> Self:
        if self.recipe_digest != canonical_digest(self):
            raise ValueError("quantization recipe digest does not match its content")
        return self


class LlamaCppQuantizationRunPaths(_Contract):
    """Absolute host paths used by one offline b10419 quantization run."""

    quantize_binary: str = Field(min_length=2, max_length=4096)
    imatrix_binary: str = Field(min_length=2, max_length=4096)
    source_bf16_gguf: str = Field(min_length=2, max_length=4096)
    calibration_text: str = Field(min_length=2, max_length=4096)
    q8_helper_gguf: str = Field(min_length=2, max_length=4096)
    imatrix_gguf: str = Field(min_length=2, max_length=4096)
    q4_k_m_control_gguf: str = Field(min_length=2, max_length=4096)
    q4_k_m_imatrix_gguf: str = Field(min_length=2, max_length=4096)
    q4_k_m_csight_mixed_gguf: str = Field(min_length=2, max_length=4096)
    q5_k_s_imatrix_gguf: str = Field(min_length=2, max_length=4096)
    mixed_tensor_type_file: str = Field(min_length=2, max_length=4096)

    @field_validator("*")
    @classmethod
    def require_absolute_safe_path(cls, value: str) -> str:
        if "\x00" in value or "\n" in value or "\r" in value:
            raise ValueError("run-plan paths cannot contain control characters")
        if not Path(value).is_absolute():
            raise ValueError("run-plan paths must be absolute")
        return value

    @model_validator(mode="after")
    def require_distinct_paths(self) -> Self:
        values = tuple(str(value) for value in self.model_dump(mode="python").values())
        if len(values) != len(set(values)):
            raise ValueError("run-plan paths must be unique")
        return self


class LlamaCppQuantizationRunCommand(_Contract):
    order: int = Field(gt=0)
    operation: Literal[
        "CREATE_Q8_0_CALIBRATION_HELPER_FROM_BF16",
        "COMPUTE_IMATRIX_ON_Q8_0_HELPER",
        "QUANTIZE_FINAL_CANDIDATE_DIRECTLY_FROM_BF16",
    ]
    argv: tuple[str, ...] = Field(min_length=2)
    input_digests: dict[str, str]
    generated_input_paths: tuple[str, ...] = ()
    output_path: str = Field(min_length=2, max_length=4096)
    expected_output_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    recipe_name: QuantizationRecipeName | None = None
    recipe_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    final_quantization_source: Literal["NOT_FINAL_OUTPUT", "BF16_GGUF"]
    allow_output_overwrite: Literal[False] = False

    @field_validator("argv")
    @classmethod
    def require_safe_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item or "\x00" in item or "\n" in item or "\r" in item for item in value):
            raise ValueError("run-plan argv entries must be non-empty and contain no controls")
        return value

    @field_validator("input_digests")
    @classmethod
    def require_input_digests(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("each run command must pin at least one input digest")
        if any(not Path(path).is_absolute() for path in value):
            raise ValueError("run-command inputs must use absolute paths")
        if any(re.fullmatch(_DIGEST_PATTERN, digest) is None for digest in value.values()):
            raise ValueError("run-command inputs must use SHA-256 digests")
        return value

    @field_validator("generated_input_paths")
    @classmethod
    def require_absolute_generated_inputs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not Path(path).is_absolute() for path in value):
            raise ValueError("generated run-command inputs must use absolute paths")
        return value


class LlamaCppQuantizationRunPlan(_Contract):
    """Strict argv plan consumed without a shell by the explicit offline runner."""

    schema_version: Literal[
        "llama_cpp_quantization_run_plan/1.0.0",
        "llama_cpp_quantization_run_plan/1.1.0",
    ] = "llama_cpp_quantization_run_plan/1.0.0"
    phase: Literal["CALIBRATION", "FINAL_CANDIDATES"]
    llama_cpp_build: Literal["b10419"] = "b10419"
    llama_cpp_revision: Literal["aee56b3abfeb134218fe5c496c329a1faac1ef28"] = (
        LLAMA_CPP_B10419_REVISION
    )
    source_bf16_gguf_digest: str = Field(pattern=_DIGEST_PATTERN)
    calibration_text_digest: str = Field(pattern=_DIGEST_PATTERN)
    calibration_helper_q8_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    imatrix_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    quantize_binary_digest: str = Field(pattern=_DIGEST_PATTERN)
    imatrix_binary_digest: str = Field(pattern=_DIGEST_PATTERN)
    mixed_tensor_type_file_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    final_candidate_set: FinalCandidateSet | None = None
    paths: LlamaCppQuantizationRunPaths
    commands: tuple[LlamaCppQuantizationRunCommand, ...] = Field(min_length=2, max_length=4)
    final_candidates_from_bf16: bool
    q8_helper_used_as_final_source: Literal[False] = False
    sealed_test_data_used: Literal[False] = False
    shell_interpolation_used: Literal[False] = False
    plan_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def require_phase_contract(self) -> Self:
        if tuple(item.order for item in self.commands) != tuple(range(1, len(self.commands) + 1)):
            raise ValueError("run-plan command order must be contiguous")
        if len({item.output_path for item in self.commands}) != len(self.commands):
            raise ValueError("run-plan command outputs must be unique")
        if self.phase == "CALIBRATION":
            if (
                self.schema_version != "llama_cpp_quantization_run_plan/1.0.0"
                or self.final_candidate_set is not None
            ):
                raise ValueError("calibration plans must retain the v1.0 schema")
            operations = tuple(item.operation for item in self.commands)
            if operations != (
                "CREATE_Q8_0_CALIBRATION_HELPER_FROM_BF16",
                "COMPUTE_IMATRIX_ON_Q8_0_HELPER",
            ):
                raise ValueError("calibration plan must create Q8_0 then compute the imatrix")
            if self.final_candidates_from_bf16:
                raise ValueError("calibration phase does not create final candidates")
            helper, imatrix = self.commands
            try:
                threads = int(helper.argv[-1])
            except (ValueError, IndexError) as error:
                raise ValueError("calibration helper threads are invalid") from error
            if threads <= 0 or threads > 256 or str(threads) != helper.argv[-1]:
                raise ValueError("calibration helper threads are invalid")
            expected_helper_argv = (
                self.paths.quantize_binary,
                self.paths.source_bf16_gguf,
                self.paths.q8_helper_gguf,
                "Q8_0",
                str(threads),
            )
            expected_imatrix_argv = (
                self.paths.imatrix_binary,
                "--model",
                self.paths.q8_helper_gguf,
                "--file",
                self.paths.calibration_text,
                "--output-file",
                self.paths.imatrix_gguf,
                "--output-format",
                "gguf",
                "--no-ppl",
                "--parse-special",
                "--process-output",
                "--output-frequency",
                str(LLAMA_CPP_IMATRIX_OUTPUT_FREQUENCY),
                "--save-frequency",
                "0",
                "--ctx-size",
                "512",
                "--batch-size",
                "512",
                "--ubatch-size",
                "128",
                "--chunks",
                "-1",
                "--threads",
                str(threads),
                "--threads-batch",
                str(threads),
                "--n-gpu-layers",
                "auto",
                "--flash-attn",
                "on",
            )
            expected_helper_inputs = {
                self.paths.quantize_binary: self.quantize_binary_digest,
                self.paths.source_bf16_gguf: self.source_bf16_gguf_digest,
            }
            expected_imatrix_inputs = {
                self.paths.imatrix_binary: self.imatrix_binary_digest,
                self.paths.calibration_text: self.calibration_text_digest,
            }
            expected_generated_inputs = (self.paths.q8_helper_gguf,)
            if self.calibration_helper_q8_digest is not None:
                expected_imatrix_inputs[self.paths.q8_helper_gguf] = (
                    self.calibration_helper_q8_digest
                )
                expected_generated_inputs = ()
            if (
                helper.argv != expected_helper_argv
                or helper.input_digests != expected_helper_inputs
                or helper.generated_input_paths
                or helper.output_path != self.paths.q8_helper_gguf
                or helper.expected_output_digest != self.calibration_helper_q8_digest
                or helper.recipe_name is not None
                or helper.recipe_digest is not None
                or imatrix.argv != expected_imatrix_argv
                or imatrix.input_digests != expected_imatrix_inputs
                or imatrix.generated_input_paths != expected_generated_inputs
                or imatrix.output_path != self.paths.imatrix_gguf
                or imatrix.expected_output_digest != self.imatrix_digest
                or imatrix.recipe_name is not None
                or imatrix.recipe_digest is not None
            ):
                raise ValueError("calibration commands differ from the pinned b10419 argv contract")
        else:
            if self.schema_version == "llama_cpp_quantization_run_plan/1.0.0":
                if self.final_candidate_set is not None:
                    raise ValueError("v1.0 final plans cannot declare a candidate subset")
                expected = (
                    QuantizationRecipeName.Q4_K_M_CONTROL,
                    QuantizationRecipeName.Q4_K_M_IMATRIX,
                    QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
                    QuantizationRecipeName.Q5_K_S_IMATRIX,
                )
            else:
                if self.final_candidate_set is not FinalCandidateSet.DEV_QUALIFICATION_PAIR:
                    raise ValueError("v1.1 final plans are limited to the Dev qualification pair")
                expected = (
                    QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
                    QuantizationRecipeName.Q5_K_S_IMATRIX,
                )
            if tuple(item.recipe_name for item in self.commands) != expected:
                raise ValueError("final plan commands differ from the declared candidate set")
            if not self.final_candidates_from_bf16:
                raise ValueError("final candidates must be quantized directly from BF16")
            output_paths = {
                QuantizationRecipeName.Q4_K_M_CONTROL: self.paths.q4_k_m_control_gguf,
                QuantizationRecipeName.Q4_K_M_IMATRIX: self.paths.q4_k_m_imatrix_gguf,
                QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED: (self.paths.q4_k_m_csight_mixed_gguf),
                QuantizationRecipeName.Q5_K_S_IMATRIX: self.paths.q5_k_s_imatrix_gguf,
            }
            final_threads: int | None = None
            for command in self.commands:
                if (
                    command.final_quantization_source != "BF16_GGUF"
                    or self.paths.source_bf16_gguf not in command.argv
                    or self.paths.q8_helper_gguf in command.argv
                    or "--allow-requantize" in command.argv
                ):
                    raise ValueError(
                        "every final command must quantize BF16 without requantization"
                    )
                try:
                    threads = int(command.argv[-1])
                except (ValueError, IndexError) as error:
                    raise ValueError("final quantization threads are invalid") from error
                if threads <= 0 or threads > 256 or str(threads) != command.argv[-1]:
                    raise ValueError("final quantization threads are invalid")
                if final_threads is None:
                    final_threads = threads
                elif final_threads != threads:
                    raise ValueError("final quantization commands must use one thread count")
                assert command.recipe_name is not None
                expected_argv: list[str] = [self.paths.quantize_binary]
                expected_inputs = {
                    self.paths.quantize_binary: self.quantize_binary_digest,
                    self.paths.source_bf16_gguf: self.source_bf16_gguf_digest,
                }
                if command.recipe_name is not QuantizationRecipeName.Q4_K_M_CONTROL:
                    if self.imatrix_digest is None:
                        raise ValueError("final imatrix candidates require a pinned imatrix")
                    expected_argv.extend(("--imatrix", self.paths.imatrix_gguf))
                    expected_inputs[self.paths.imatrix_gguf] = self.imatrix_digest
                if command.recipe_name is QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED:
                    if self.mixed_tensor_type_file_digest is None:
                        raise ValueError("mixed candidate requires a pinned tensor-type file")
                    expected_argv.extend(("--tensor-type-file", self.paths.mixed_tensor_type_file))
                    expected_inputs[self.paths.mixed_tensor_type_file] = (
                        self.mixed_tensor_type_file_digest
                    )
                default_type = (
                    "Q5_K_S"
                    if command.recipe_name is QuantizationRecipeName.Q5_K_S_IMATRIX
                    else "Q4_K_M"
                )
                expected_argv.extend(
                    (
                        self.paths.source_bf16_gguf,
                        output_paths[command.recipe_name],
                        default_type,
                        str(threads),
                    )
                )
                if (
                    command.argv != tuple(expected_argv)
                    or command.input_digests != expected_inputs
                    or command.generated_input_paths
                    or command.output_path != output_paths[command.recipe_name]
                    or command.recipe_digest is None
                ):
                    raise ValueError("final command differs from the pinned b10419 argv contract")
        digest_exclusions = {"plan_digest"}
        if self.schema_version == "llama_cpp_quantization_run_plan/1.0.0":
            # Preserve byte-for-byte digest compatibility with plans emitted before
            # ``final_candidate_set`` was added in the additive v1.1 contract.
            digest_exclusions.add("final_candidate_set")
        expected_digest = canonical_digest(self.model_dump(mode="json", exclude=digest_exclusions))
        if self.plan_digest != expected_digest:
            raise ValueError("run-plan digest does not match its canonical content")
        return self


def canonical_digest(value: BaseModel | Mapping[str, object] | Sequence[object]) -> str:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json", exclude={"recipe_digest"})
    else:
        payload = _jsonable(value)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    return value


def normalize_for_safety(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def render_qwen38_text_chat(messages: Sequence[ChatMessage]) -> str:
    """Render the exact text-only, no-tools, non-thinking branch of the pinned template."""

    if not messages:
        raise QuantizationAssetError("no messages provided")
    rendered: list[str] = []
    for index, message in enumerate(messages):
        content = message.content.strip()
        if message.role is ChatRole.SYSTEM:
            if index != 0:
                raise QuantizationAssetError("system message must be at the beginning")
            rendered.append(f"<|im_start|>system\n{content}<|im_end|>\n")
        elif message.role is ChatRole.USER:
            rendered.append(f"<|im_start|>user\n{content}<|im_end|>\n")
        elif message.role is ChatRole.ASSISTANT:
            rendered.append(f"<|im_start|>assistant\n{content}<|im_end|>\n")
        else:  # pragma: no cover - StrEnum validation makes this defensive only.
            raise QuantizationAssetError("unsupported chat role")
    return "".join(rendered)


_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-z]{2,}")),
    ("KOREAN_PHONE", re.compile(r"(?<!\d)01[016789][ -]?\d{3,4}[ -]?\d{4}(?!\d)")),
    ("KOREAN_RRN", re.compile(r"(?<!\d)\d{6}[ -]?[1-8]\d{6}(?!\d)")),
    ("PAYMENT_CARD", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    ("IPV4", re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")),
    (
        "KOREAN_STREET_ADDRESS",
        re.compile(r"[가-힣]{2,}(?:시|도)\s+[가-힣0-9-]{1,}(?:로|길)\s*\d{1,5}"),
    ),
)


def pii_finding_codes(text: str) -> tuple[str, ...]:
    return tuple(code for code, pattern in _PII_PATTERNS if pattern.search(text) is not None)


def _word_shingles(value: str, width: int = 8) -> set[str]:
    words = normalize_for_safety(value).split()
    if len(words) < width:
        return set()
    return {
        hashlib.sha256(" ".join(words[index : index + width]).encode()).hexdigest()
        for index in range(len(words) - width + 1)
    }


class TestLeakageIndex:
    """Content-only holdout index; it never retains identifiers in generated manifests."""

    def __init__(self, values: Iterable[str]) -> None:
        normalized = tuple(
            item for value in values if len(item := normalize_for_safety(value)) >= 12
        )
        self._digests = {hashlib.sha256(value.encode()).hexdigest() for value in normalized}
        counts: Counter[str] = Counter()
        for value in normalized:
            counts.update(_word_shingles(value))
        self._shingles = set(counts)

    def overlaps(self, text: str) -> bool:
        normalized = normalize_for_safety(text)
        if hashlib.sha256(normalized.encode()).hexdigest() in self._digests:
            return True
        candidate = _word_shingles(normalized)
        return len(candidate & self._shingles) >= 4


def string_leaves(value: object) -> tuple[str, ...]:
    leaves: list[str] = []
    if isinstance(value, str):
        leaves.append(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            leaves.extend(string_leaves(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            leaves.extend(string_leaves(item))
    return tuple(leaves)


def build_quantization_corpus(
    *,
    plan: QuantizationCorpusPlan,
    records: Iterable[NormalizedCorpusRecord],
    tokenizer: TokenizerPort,
    test_leakage_index: TestLeakageIndex,
) -> CorpusBuild:
    """Build exact token-budget splits, with source, PII, dedupe, and Test isolation gates."""

    if tokenizer.identity_digest != plan.chat_template.tokenizer_runtime_identity_digest:
        raise QuantizationAssetError("tokenizer runtime identity does not match the frozen plan")
    pins = {item.source_id: item for item in plan.sources}
    accepted_by_category: dict[
        MixCategory, list[tuple[NormalizedCorpusRecord, str, tuple[int, ...]]]
    ] = defaultdict(list)
    seen_content: set[str] = set()
    rejections: Counter[str] = Counter()
    input_count = 0
    for record in records:
        input_count += 1
        pin = pins.get(record.source_id)
        if (
            pin is None
            or pin.revision != record.source_revision
            or pin.category is not record.category
            or pin.license_identifier != record.license_identifier
        ):
            rejections["source"] += 1
            continue
        text = render_qwen38_text_chat(record.messages)
        if pii_finding_codes(text):
            rejections["pii"] += 1
            continue
        if test_leakage_index.overlaps(text):
            rejections["test"] += 1
            continue
        content_digest = hashlib.sha256(normalize_for_safety(text).encode()).hexdigest()
        if content_digest in seen_content:
            rejections["duplicate"] += 1
            continue
        token_ids = tokenizer.encode(text)
        if not token_ids:
            rejections["source"] += 1
            continue
        seen_content.add(content_digest)
        accepted_by_category[record.category].append((record, text, token_ids))

    samples: list[PreparedCorpusSample] = []
    used_record_hashes: set[str] = set()
    split_order = (
        CorpusSplit.LOGITS_HOLDOUT,
        CorpusSplit.PPL_HOLDOUT,
        CorpusSplit.CALIBRATION,
    )
    for category in MixCategory:
        pool = sorted(
            accepted_by_category[category],
            key=lambda item: hashlib.sha256(
                f"{plan.seed}|{item[0].source_id}|{item[0].record_id}".encode()
            ).digest(),
        )
        cursor = 0
        for split in split_order:
            remaining = plan.target_for(split, category)
            while remaining > 0 and cursor < len(pool):
                record, text, token_ids = pool[cursor]
                cursor += 1
                selected_tokens = token_ids
                selected_text = text
                truncated = False
                if len(selected_tokens) > remaining:
                    selected_tokens = selected_tokens[:remaining]
                    selected_text = tokenizer.decode(selected_tokens)
                    if tokenizer.encode(selected_text) != selected_tokens:
                        raise QuantizationAssetError(
                            "tokenizer decode/encode round-trip failed at an exact split boundary"
                        )
                    truncated = True
                record_hash = (
                    "sha256:"
                    + hashlib.sha256(f"{record.source_id}|{record.record_id}".encode()).hexdigest()
                )
                if record_hash in used_record_hashes:
                    raise QuantizationAssetError("a source record crossed corpus splits")
                used_record_hashes.add(record_hash)
                samples.append(
                    PreparedCorpusSample(
                        record_id_hash=record_hash,
                        source_id=record.source_id,
                        source_revision=record.source_revision,
                        category=category,
                        split=split,
                        token_count=len(selected_tokens),
                        content_digest=(
                            "sha256:" + hashlib.sha256(selected_text.encode()).hexdigest()
                        ),
                        text=selected_text,
                        truncated=truncated,
                    )
                )
                remaining -= len(selected_tokens)
            if remaining:
                raise QuantizationAssetError(
                    f"insufficient screened tokens for {category.value}/{split.value}: {remaining}"
                )

    _validate_built_corpus(plan, samples, tokenizer, test_leakage_index)
    return CorpusBuild(
        samples=tuple(samples),
        safety=CorpusSafetyReport(
            input_records=input_count,
            accepted_records=len(samples),
            duplicate_rejections=rejections["duplicate"],
            pii_rejections=rejections["pii"],
            test_overlap_rejections=rejections["test"],
            source_contract_rejections=rejections["source"],
        ),
    )


def _validate_built_corpus(
    plan: QuantizationCorpusPlan,
    samples: Sequence[PreparedCorpusSample],
    tokenizer: TokenizerPort,
    test_leakage_index: TestLeakageIndex,
) -> None:
    record_hashes = [item.record_id_hash for item in samples]
    if len(record_hashes) != len(set(record_hashes)):
        raise QuantizationAssetError("source records overlap across output splits")
    content_digests = [item.content_digest for item in samples]
    if len(content_digests) != len(set(content_digests)):
        raise QuantizationAssetError("output corpus contains duplicate content")
    for split in CorpusSplit:
        for category in MixCategory:
            actual = sum(
                item.token_count
                for item in samples
                if item.split is split and item.category is category
            )
            expected = plan.target_for(split, category)
            if actual != expected:
                raise QuantizationAssetError(
                    "token target mismatch for "
                    f"{split.value}/{category.value}: {actual}!={expected}"
                )
    for item in samples:
        if pii_finding_codes(item.text):
            raise QuantizationAssetError("PII was found in an output sample")
        if test_leakage_index.overlaps(item.text):
            raise QuantizationAssetError("Test overlap was found in an output sample")
        if len(tokenizer.encode(item.text)) != item.token_count:
            raise QuantizationAssetError("stored token count does not match the pinned tokenizer")


def compile_quantization_recipe(
    *,
    name: QuantizationRecipeName,
    inventory: TensorInventory,
    llama_cpp_revision: str,
    calibration_manifest_digest: str | None,
    imatrix_digest: str | None,
    calibration_helper_q8_digest: str | None = None,
) -> CompiledQuantizationRecipe:
    """Compile a complete deterministic tensor assignment for one frozen candidate."""

    if re.fullmatch(_REVISION_PATTERN, llama_cpp_revision) is None:
        raise QuantizationAssetError("llama.cpp revision must be an exact 40-character commit")
    imatrix_required = name is not QuantizationRecipeName.Q4_K_M_CONTROL
    if imatrix_required and (
        imatrix_digest is None
        or calibration_manifest_digest is None
        or calibration_helper_q8_digest is None
    ):
        raise QuantizationAssetError(
            "imatrix recipes require calibration, Q8 helper, and imatrix digests"
        )
    if not imatrix_required and (
        imatrix_digest is not None or calibration_helper_q8_digest is not None
    ):
        raise QuantizationAssetError("the control recipe must not use an imatrix or Q8 helper")
    default_type: Literal["Q4_K_M", "Q5_K_S"] = (
        "Q5_K_S" if name is QuantizationRecipeName.Q5_K_S_IMATRIX else "Q4_K_M"
    )
    overrides: list[TensorQuantization] = []
    if name is QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED:
        edge_blocks = set(range(min(3, inventory.block_count))) | set(
            range(max(0, inventory.block_count - 3), inventory.block_count)
        )
        for tensor in inventory.tensors:
            target: str | None = None
            rationale: str | None = None
            block_match = re.match(r"^blk\.(\d+)\.", tensor.name)
            if tensor.name in {"token_embd.weight", "output.weight"}:
                target, rationale = "Q6_K", "preserve input/output lexical projection"
            elif block_match is not None and int(block_match.group(1)) in edge_blocks:
                target, rationale = "Q6_K", "preserve first/last transformer blocks"
            elif any(
                marker in tensor.name for marker in ("ffn_gate.weight", "attn_gate", "ssm", "state")
            ):
                target, rationale = "Q6_K", "preserve gate or recurrent state tensor"
            if target is not None and rationale is not None:
                overrides.append(
                    TensorQuantization(
                        tensor_name=tensor.name,
                        target_type=target,
                        rationale=rationale,
                    )
                )
    values: dict[str, object] = {
        "schema_version": "gguf_quantization_recipe/1.0.0",
        "recipe_name": name,
        "source_gguf_digest": inventory.source_gguf_digest,
        "tensor_inventory_digest": canonical_digest(inventory),
        "calibration_manifest_digest": calibration_manifest_digest,
        "imatrix_digest": imatrix_digest,
        "calibration_helper_q8_digest": calibration_helper_q8_digest,
        "default_type": default_type,
        "overrides": tuple(overrides),
        "llama_cpp_revision": llama_cpp_revision,
        "quantization_source": "BF16_GGUF",
        "imatrix_compute_source": "Q8_0_HELPER" if imatrix_required else "NONE",
        "allow_output_overwrite": False,
        "test_data_used_for_quantization": False,
    }
    values["recipe_digest"] = canonical_digest(values)
    return CompiledQuantizationRecipe.model_validate(values)


def compile_calibration_helper_recipe(
    *,
    inventory: TensorInventory,
    llama_cpp_revision: str,
) -> CalibrationHelperRecipe:
    """Describe the Q8_0 helper used only to make imatrix computation practical.

    Final Q4/Q5 outputs must still be quantized directly from ``source_bf16_gguf_digest``.
    """

    if re.fullmatch(_REVISION_PATTERN, llama_cpp_revision) is None:
        raise QuantizationAssetError("llama.cpp revision must be an exact 40-character commit")
    values: dict[str, object] = {
        "schema_version": "gguf_calibration_helper_recipe/1.0.0",
        "source_bf16_gguf_digest": inventory.source_gguf_digest,
        "tensor_inventory_digest": canonical_digest(inventory),
        "helper_type": "Q8_0",
        "llama_cpp_revision": llama_cpp_revision,
        "helper_purpose": "IMATRIX_COMPUTE_ONLY",
        "final_quantization_source": "BF16_GGUF",
        "allow_output_overwrite": False,
    }
    values["recipe_digest"] = canonical_digest(values)
    return CalibrationHelperRecipe.model_validate(values)


def render_llama_cpp_tensor_type_file(recipe: CompiledQuantizationRecipe) -> str:
    """Render exact, anchored b10419 regex overrides without shell syntax.

    ``llama-quantize`` treats tensor names from ``--tensor-type-file`` as regular
    expressions. Escaping and anchoring each inventory name prevents a dot or a
    partial name from selecting an unintended tensor.
    """

    if recipe.recipe_name is not QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED:
        raise QuantizationAssetError("only the accepted mixed recipe has tensor overrides")
    if not recipe.overrides:
        raise QuantizationAssetError("the mixed recipe has no tensor overrides")
    names = tuple(item.tensor_name for item in recipe.overrides)
    if len(names) != len(set(names)):
        raise QuantizationAssetError("the mixed recipe contains duplicate tensor overrides")
    return "".join(
        f"^{re.escape(item.tensor_name)}$={item.target_type.casefold()}\n"
        for item in sorted(recipe.overrides, key=lambda value: value.tensor_name)
    )


def compile_llama_cpp_b10419_calibration_run_plan(
    *,
    paths: LlamaCppQuantizationRunPaths,
    source_bf16_gguf_digest: str,
    calibration_text_digest: str,
    quantize_binary_digest: str,
    imatrix_binary_digest: str,
    threads: int,
    expected_helper_q8_digest: str | None = None,
    expected_imatrix_digest: str | None = None,
) -> LlamaCppQuantizationRunPlan:
    """Build the executable Q8-helper then imatrix phase for llama.cpp b10419."""

    _validate_run_plan_inputs(
        source_bf16_gguf_digest=source_bf16_gguf_digest,
        calibration_text_digest=calibration_text_digest,
        quantize_binary_digest=quantize_binary_digest,
        imatrix_binary_digest=imatrix_binary_digest,
        threads=threads,
    )
    for optional_digest in (expected_helper_q8_digest, expected_imatrix_digest):
        if optional_digest is not None and re.fullmatch(_DIGEST_PATTERN, optional_digest) is None:
            raise QuantizationAssetError("expected calibration outputs must use SHA-256 digests")
    q8_inputs = {
        paths.quantize_binary: quantize_binary_digest,
        paths.source_bf16_gguf: source_bf16_gguf_digest,
    }
    imatrix_inputs = {
        paths.imatrix_binary: imatrix_binary_digest,
        paths.calibration_text: calibration_text_digest,
    }
    generated_inputs: tuple[str, ...] = (paths.q8_helper_gguf,)
    if expected_helper_q8_digest is not None:
        imatrix_inputs[paths.q8_helper_gguf] = expected_helper_q8_digest
        generated_inputs = ()
    commands = (
        LlamaCppQuantizationRunCommand(
            order=1,
            operation="CREATE_Q8_0_CALIBRATION_HELPER_FROM_BF16",
            argv=(
                paths.quantize_binary,
                paths.source_bf16_gguf,
                paths.q8_helper_gguf,
                "Q8_0",
                str(threads),
            ),
            input_digests=q8_inputs,
            output_path=paths.q8_helper_gguf,
            expected_output_digest=expected_helper_q8_digest,
            final_quantization_source="NOT_FINAL_OUTPUT",
        ),
        LlamaCppQuantizationRunCommand(
            order=2,
            operation="COMPUTE_IMATRIX_ON_Q8_0_HELPER",
            argv=(
                paths.imatrix_binary,
                "--model",
                paths.q8_helper_gguf,
                "--file",
                paths.calibration_text,
                "--output-file",
                paths.imatrix_gguf,
                "--output-format",
                "gguf",
                "--no-ppl",
                "--parse-special",
                "--process-output",
                "--output-frequency",
                str(LLAMA_CPP_IMATRIX_OUTPUT_FREQUENCY),
                "--save-frequency",
                "0",
                "--ctx-size",
                "512",
                "--batch-size",
                "512",
                "--ubatch-size",
                "128",
                "--chunks",
                "-1",
                "--threads",
                str(threads),
                "--threads-batch",
                str(threads),
                "--n-gpu-layers",
                "auto",
                "--flash-attn",
                "on",
            ),
            input_digests=imatrix_inputs,
            generated_input_paths=generated_inputs,
            output_path=paths.imatrix_gguf,
            expected_output_digest=expected_imatrix_digest,
            final_quantization_source="NOT_FINAL_OUTPUT",
        ),
    )
    values: dict[str, object] = {
        "schema_version": "llama_cpp_quantization_run_plan/1.0.0",
        "phase": "CALIBRATION",
        "llama_cpp_build": LLAMA_CPP_B10419_BUILD,
        "llama_cpp_revision": LLAMA_CPP_B10419_REVISION,
        "source_bf16_gguf_digest": source_bf16_gguf_digest,
        "calibration_text_digest": calibration_text_digest,
        "calibration_helper_q8_digest": expected_helper_q8_digest,
        "imatrix_digest": expected_imatrix_digest,
        "quantize_binary_digest": quantize_binary_digest,
        "imatrix_binary_digest": imatrix_binary_digest,
        "mixed_tensor_type_file_digest": None,
        "paths": paths,
        "commands": commands,
        "final_candidates_from_bf16": False,
        "q8_helper_used_as_final_source": False,
        "sealed_test_data_used": False,
        "shell_interpolation_used": False,
    }
    values["plan_digest"] = canonical_digest(values)
    return LlamaCppQuantizationRunPlan.model_validate(values)


def compile_llama_cpp_b10419_final_run_plan(
    *,
    paths: LlamaCppQuantizationRunPaths,
    recipes: Sequence[CompiledQuantizationRecipe],
    calibration_text_digest: str,
    quantize_binary_digest: str,
    imatrix_binary_digest: str,
    mixed_tensor_type_file_digest: str,
    threads: int,
    expected_output_digests: Mapping[QuantizationRecipeName, str] | None = None,
    final_candidate_set: FinalCandidateSet = FinalCandidateSet.FOUR_WAY_COMPARISON,
) -> LlamaCppQuantizationRunPlan:
    """Build one admitted final output set, each candidate sourced directly from BF16."""

    expected_names = (
        (
            QuantizationRecipeName.Q4_K_M_CONTROL,
            QuantizationRecipeName.Q4_K_M_IMATRIX,
            QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
            QuantizationRecipeName.Q5_K_S_IMATRIX,
        )
        if final_candidate_set is FinalCandidateSet.FOUR_WAY_COMPARISON
        else (
            QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED,
            QuantizationRecipeName.Q5_K_S_IMATRIX,
        )
    )
    by_name = {item.recipe_name: item for item in recipes}
    if len(recipes) != len(by_name) or tuple(by_name) != expected_names:
        raise QuantizationAssetError("final run plan recipes differ from the selected output set")
    source_digests = {item.source_gguf_digest for item in recipes}
    revisions = {item.llama_cpp_revision for item in recipes}
    calibration_manifests = {
        item.calibration_manifest_digest
        for item in recipes
        if item.calibration_manifest_digest is not None
    }
    helper_digests = {
        item.calibration_helper_q8_digest
        for item in recipes
        if item.calibration_helper_q8_digest is not None
    }
    imatrix_digests = {item.imatrix_digest for item in recipes if item.imatrix_digest is not None}
    if len(source_digests) != 1 or revisions != {LLAMA_CPP_B10419_REVISION}:
        raise QuantizationAssetError("final recipes must share the pinned BF16 and b10419 revision")
    if len(calibration_manifests) != 1 or len(helper_digests) != 1 or len(imatrix_digests) != 1:
        raise QuantizationAssetError(
            "final recipes must share calibration, helper, and imatrix evidence"
        )
    source_digest = next(iter(source_digests))
    helper_digest = next(iter(helper_digests))
    imatrix_digest = next(iter(imatrix_digests))
    assert helper_digest is not None
    assert imatrix_digest is not None
    _validate_run_plan_inputs(
        source_bf16_gguf_digest=source_digest,
        calibration_text_digest=calibration_text_digest,
        quantize_binary_digest=quantize_binary_digest,
        imatrix_binary_digest=imatrix_binary_digest,
        threads=threads,
    )
    if re.fullmatch(_DIGEST_PATTERN, mixed_tensor_type_file_digest) is None:
        raise QuantizationAssetError("tensor-type file must use a SHA-256 digest")
    outputs = {
        QuantizationRecipeName.Q4_K_M_CONTROL: paths.q4_k_m_control_gguf,
        QuantizationRecipeName.Q4_K_M_IMATRIX: paths.q4_k_m_imatrix_gguf,
        QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED: paths.q4_k_m_csight_mixed_gguf,
        QuantizationRecipeName.Q5_K_S_IMATRIX: paths.q5_k_s_imatrix_gguf,
    }
    expected_outputs = dict(expected_output_digests or {})
    if not set(expected_outputs) <= set(expected_names):
        raise QuantizationAssetError("unexpected final candidate output digest key")
    if any(re.fullmatch(_DIGEST_PATTERN, digest) is None for digest in expected_outputs.values()):
        raise QuantizationAssetError("expected final outputs must use SHA-256 digests")
    commands: list[LlamaCppQuantizationRunCommand] = []
    for order, name in enumerate(expected_names, start=1):
        recipe = by_name[name]
        argv: list[str] = [paths.quantize_binary]
        input_digests = {
            paths.quantize_binary: quantize_binary_digest,
            paths.source_bf16_gguf: source_digest,
        }
        if name is not QuantizationRecipeName.Q4_K_M_CONTROL:
            argv.extend(("--imatrix", paths.imatrix_gguf))
            input_digests[paths.imatrix_gguf] = imatrix_digest
        if name is QuantizationRecipeName.Q4_K_M_CSIGHT_MIXED:
            argv.extend(("--tensor-type-file", paths.mixed_tensor_type_file))
            input_digests[paths.mixed_tensor_type_file] = mixed_tensor_type_file_digest
        argv.extend(
            (
                paths.source_bf16_gguf,
                outputs[name],
                recipe.default_type,
                str(threads),
            )
        )
        commands.append(
            LlamaCppQuantizationRunCommand(
                order=order,
                operation="QUANTIZE_FINAL_CANDIDATE_DIRECTLY_FROM_BF16",
                argv=tuple(argv),
                input_digests=input_digests,
                output_path=outputs[name],
                expected_output_digest=expected_outputs.get(name),
                recipe_name=name,
                recipe_digest=recipe.recipe_digest,
                final_quantization_source="BF16_GGUF",
            )
        )
    values: dict[str, object] = {
        "schema_version": (
            "llama_cpp_quantization_run_plan/1.0.0"
            if final_candidate_set is FinalCandidateSet.FOUR_WAY_COMPARISON
            else "llama_cpp_quantization_run_plan/1.1.0"
        ),
        "phase": "FINAL_CANDIDATES",
        "llama_cpp_build": LLAMA_CPP_B10419_BUILD,
        "llama_cpp_revision": LLAMA_CPP_B10419_REVISION,
        "source_bf16_gguf_digest": source_digest,
        "calibration_text_digest": calibration_text_digest,
        "calibration_helper_q8_digest": helper_digest,
        "imatrix_digest": imatrix_digest,
        "quantize_binary_digest": quantize_binary_digest,
        "imatrix_binary_digest": imatrix_binary_digest,
        "mixed_tensor_type_file_digest": mixed_tensor_type_file_digest,
        "paths": paths,
        "commands": tuple(commands),
        "final_candidates_from_bf16": True,
        "q8_helper_used_as_final_source": False,
        "sealed_test_data_used": False,
        "shell_interpolation_used": False,
    }
    if final_candidate_set is FinalCandidateSet.DEV_QUALIFICATION_PAIR:
        values["final_candidate_set"] = final_candidate_set
    values["plan_digest"] = canonical_digest(values)
    return LlamaCppQuantizationRunPlan.model_validate(values)


def _validate_run_plan_inputs(
    *,
    source_bf16_gguf_digest: str,
    calibration_text_digest: str,
    quantize_binary_digest: str,
    imatrix_binary_digest: str,
    threads: int,
) -> None:
    if threads <= 0 or threads > 256:
        raise QuantizationAssetError("quantization threads must be between 1 and 256")
    for digest in (
        source_bf16_gguf_digest,
        calibration_text_digest,
        quantize_binary_digest,
        imatrix_binary_digest,
    ):
        if re.fullmatch(_DIGEST_PATTERN, digest) is None:
            raise QuantizationAssetError("run-plan inputs must use SHA-256 digests")


__all__ = [
    "LLAMA_CPP_B10419_BUILD",
    "LLAMA_CPP_B10419_REVISION",
    "LLAMA_CPP_IMATRIX_OUTPUT_FREQUENCY",
    "CalibrationHelperRecipe",
    "ChatMessage",
    "ChatRole",
    "ChatTemplateContract",
    "CompiledQuantizationRecipe",
    "CorpusArtifact",
    "CorpusBuild",
    "CorpusSafetyReport",
    "CorpusSplit",
    "FinalCandidateSet",
    "LlamaCppQuantizationRunCommand",
    "LlamaCppQuantizationRunPaths",
    "LlamaCppQuantizationRunPlan",
    "MixCategory",
    "MixQuota",
    "NormalizedCorpusRecord",
    "PreparedCorpusSample",
    "QuantizationAssetError",
    "QuantizationCorpusManifest",
    "QuantizationCorpusPlan",
    "QuantizationRecipeName",
    "SourceKind",
    "SourcePin",
    "TensorInfo",
    "TensorInventory",
    "TensorQuantization",
    "TestLeakageIndex",
    "TokenizerPort",
    "build_quantization_corpus",
    "canonical_digest",
    "compile_calibration_helper_recipe",
    "compile_llama_cpp_b10419_calibration_run_plan",
    "compile_llama_cpp_b10419_final_run_plan",
    "compile_quantization_recipe",
    "normalize_for_safety",
    "pii_finding_codes",
    "render_llama_cpp_tensor_type_file",
    "render_qwen38_text_chat",
    "string_leaves",
]
