"""Seed ten realistic internal demo cases and run real E3 through local CSight Core.

The command is deliberately local/test-only.  It never accepts a plaintext password:
it resolves one existing active ADMIN from the local database and issues a short-lived
token in memory with the configured local JWT codec.  Raw images stay outside Git and
are uploaded through the normal private Evidence API.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, Self, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import Engine, and_, func, select
from sqlalchemy.engine import make_url

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    CaseResolutionModel,
    ExternalActionIntentModel,
    ExternalActionSimulationAttemptModel,
    ExternalActionSimulationResultModel,
    GroundedExplanationRunModel,
    HumanReviewDecisionModel,
    HumanReviewTaskModel,
    PolicyEvaluationRunModel,
    PolicyRetrievalRunModel,
    RoleModel,
    TenantModel,
    UserModel,
    UserRoleModel,
)
from app.adapters.security import PyJWTAccessTokenCodec
from app.bootstrap.settings import Settings
from app.platform.commerce_context import validate_synthetic_commerce_context
from app.platform.poc_demo_selection import (
    PocClosedSetError,
    PocClosedSetRegistry,
    PocSourceKind,
    assess_poc_admission,
    load_poc_closed_set_registry,
)
from scripts.evaluate_e3_normal_reference import (
    SAFE_INTERNAL_DEMO_RANKS,
    NormalReferenceFailure,
    ValidatedNormalReference,
    validate_normal_reference,
)
from scripts.evaluate_e3_top100_replay import (
    EXPECTED_MODEL_NAME,
    EXPECTED_MODEL_REVISION,
    EXPECTED_MODEL_VERSION,
    EXPECTED_THRESHOLD,
    VISION_TASK,
    Top100ReplayFailure,
    ValidatedPackage,
    validate_package,
)
from scripts.smoke_scenario_vision import (
    ScenarioVisionSmokeFailure,
    json_request,
    required_string,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_V1 = ROOT / "evaluation/realistic_internal_demo_v1/manifest.json"
DEFAULT_MANIFEST_V2 = ROOT / "evaluation/realistic_internal_demo_v2/manifest.json"
DEFAULT_MANIFEST_V3 = ROOT / "evaluation/realistic_internal_demo_v3/manifest.json"
DEFAULT_MANIFEST = DEFAULT_MANIFEST_V1
DEFAULT_CLOSED_SET_REGISTRY = ROOT / "evaluation/poc_closed_set_v1/registry.json"
DEFAULT_CLOSED_SET_REGISTRY_V2 = ROOT / "evaluation/poc_closed_set_v2/registry.json"
DEFAULT_OUTPUT_V1 = ROOT / "local-data/realistic-internal-demo-v1/seed_report.json"
DEFAULT_OUTPUT_V2 = ROOT / "local-data/realistic-internal-demo-v2/seed_report.json"
DEFAULT_OUTPUT_V3 = ROOT / "local-data/realistic-internal-demo-v3/seed_report.json"
DEFAULT_OUTPUT = DEFAULT_OUTPUT_V1
DATASET_ID_V1 = "realistic-internal-demo-v1"
DATASET_ID_V2 = "realistic-internal-demo-v2"
DATASET_ID_V3 = "realistic-internal-demo-v3"
DATASET_ID = DATASET_ID_V1
DEFECT_RANKS = (3, 32, 54, 58, 78, 80)
NORMAL_REFERENCE_RANKS = (2, 8, 17, 23)
DEFECT_RANKS_V3 = (1, 9, 22, 31, 73, 79)
NORMAL_REFERENCE_RANKS_V3 = (1, 20, 65, 67)
TERMINAL_ANALYSIS_STATUSES = frozenset({"SUCCEEDED", "PARTIAL_SUCCESS", "FAILED"})
REQUESTED_ACTIONS = frozenset(
    {"EXCHANGE", "REFUND", "RETURN", "REPAIR", "INFORMATION", "OTHER", "UNSPECIFIED"}
)
PROHIBITED_COMMERCE_NAMES = (
    "쿠팡",
    "아마존",
    "네이버쇼핑",
    "11번가",
    "g마켓",
    "옥션",
    "알리익스프레스",
    "테무",
    "coupang",
    "amazon",
)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+")
PHONE_PATTERN = re.compile(r"(?<!\d)0\d{1,2}[- ]?\d{3,4}[- ]?\d{4}(?!\d)")
BOUNDARY_COUNT_KEYS = (
    "policy_retrieval_runs",
    "grounded_explanation_runs",
    "policy_evaluation_runs",
    "human_review_tasks",
    "human_review_decisions",
    "case_resolutions",
    "external_action_intents",
    "external_action_simulation_attempts",
    "external_action_simulation_results",
)
_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class RealisticDemoSeedFailure(RuntimeError):
    """Sanitized fail-closed error for the internal seed command."""


SourceKind = Literal["TOP100_SELECTED_CORRECT_DEFECT", "USER_SUPPLIED_NORMAL_REFERENCE"]
SourceGrade = Literal["KAPUTT_SELECTED_CORRECT_POSITIVE", "USER_SUPPLIED_NORMAL_REFERENCE"]
AssessmentOutcome = Literal["HIGH_CONFIDENCE_DEFECT_CANDIDATE", "BELOW_HIGH_CONFIDENCE_THRESHOLD"]


class DemoSource(BaseModel):
    model_config = _MODEL_CONFIG

    kind: SourceKind
    rank: int = Field(ge=1)
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_grade: SourceGrade
    expected_e3_outcome: AssessmentOutcome
    rights_status: Literal["INTERNAL_RESTRICTED_PROVENANCE_UNVERIFIED"]
    selection_bias: Literal[
        "POSITIVE_ONLY_CORRECT_ONLY_HIGH_CONFIDENCE",
        "LOW_SCORE_WITHIN_PIXEL_REVIEWED_INTERNAL_ALLOWLIST",
    ]

    @model_validator(mode="after")
    def require_kind_specific_boundaries(self) -> Self:
        if self.kind == "TOP100_SELECTED_CORRECT_DEFECT":
            expected = (
                "KAPUTT_SELECTED_CORRECT_POSITIVE",
                "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
                "POSITIVE_ONLY_CORRECT_ONLY_HIGH_CONFIDENCE",
            )
        else:
            expected = (
                "USER_SUPPLIED_NORMAL_REFERENCE",
                "BELOW_HIGH_CONFIDENCE_THRESHOLD",
                "LOW_SCORE_WITHIN_PIXEL_REVIEWED_INTERNAL_ALLOWLIST",
            )
        actual = (self.source_grade, self.expected_e3_outcome, self.selection_bias)
        if actual != expected:
            raise ValueError("source grade, outcome, and selection bias do not match source kind")
        return self


class DemoCaseInput(BaseModel):
    model_config = _MODEL_CONFIG

    order_ref: str = Field(min_length=1, max_length=200)
    product_ref: str = Field(min_length=1, max_length=200)
    customer_message: str = Field(min_length=20, max_length=20_000)
    requested_action: str
    attributes: dict[str, object]

    @model_validator(mode="after")
    def require_supported_case_fields(self) -> Self:
        if self.requested_action not in REQUESTED_ACTIONS:
            raise ValueError("requested_action is not supported by the Case contract")
        if self.attributes.get("product_category") != "GENERAL":
            raise ValueError("demo Case product_category must stay on the non-policy GENERAL scope")
        if "realistic_demo" in self.attributes or "realistic_internal_demo" in self.attributes:
            raise ValueError("provenance attributes are reserved for the seed command")
        context_value = self.attributes.get("synthetic_commerce_context")
        if context_value is None:
            return self
        context = validate_synthetic_commerce_context(context_value)
        external = self.attributes.get("external_action_input")
        if not isinstance(external, dict):
            raise ValueError("external_action_input must be an object")
        if self.requested_action == "REFUND":
            try:
                explicit_amount = Decimal(str(external.get("amount")))
            except (InvalidOperation, TypeError, ValueError):
                raise ValueError("refund demo requires an explicit decimal amount") from None
            if external.get("currency") != context.order.currency:
                raise ValueError("refund currency must match the synthetic paid currency")
            if explicit_amount != context.order.paid_amount:
                raise ValueError("explicit refund amount must match the synthetic paid amount")
        shipping_ref = external.get("shipping_address_ref")
        if shipping_ref is not None and shipping_ref != context.delivery.shipping_address_ref:
            raise ValueError("external shipping reference must match the synthetic delivery")
        return self


class DemoCase(BaseModel):
    model_config = _MODEL_CONFIG

    demo_id: str = Field(pattern=r"^REAL-DEMO-(V[23]-)?(DEFECT|NORMAL)-[0-9]{2}$")
    source: DemoSource
    case_input: DemoCaseInput


class DemoSelection(BaseModel):
    model_config = _MODEL_CONFIG

    total_count: Literal[10]
    defect_selected_correct_count: Literal[6]
    normal_reference_count: Literal[4]
    defect_ranks: tuple[int, ...]
    normal_reference_ranks: tuple[int, ...]
    ratio: Literal["6:4"]


class DemoBoundaries(BaseModel):
    model_config = _MODEL_CONFIG

    scenario_type: Literal["SYNTHETIC_CUSTOMER_NARRATIVE_WITH_REAL_E3_INFERENCE"]
    policy_input_linkage: Literal["NOT_LINKED_TO_POLICY_INPUT"]
    final_decision_owner: Literal["AUTHENTICATED_HUMAN_ONLY"]
    external_action_mode: Literal["NOT_RUN"]
    normal_confirmation_supported: Literal[False]
    public_redistribution_allowed: Literal[False]


class DemoNarrativeContract(BaseModel):
    model_config = _MODEL_CONFIG

    display_label: Literal["문의 내용"]
    locale: Literal["ko-KR"]
    commerce_context: Literal["FICTIONAL_MULTI_SELLER_ECOMMERCE"]
    min_sentence_count: Literal[3]
    max_sentence_count: Literal[5]
    real_company_affiliation_claimed: Literal[False]
    revision: Literal[
        "VISUAL_ALIGNED_R1",
        "COMMERCE_CONTEXT_R2",
        "COMMERCE_CONTEXT_R2_E3",
        "CLOSED_SET_EXPANSION_R3",
    ]


class DemoManifest(BaseModel):
    model_config = _MODEL_CONFIG

    schema_version: Literal["1.0.0", "2.0.0", "3.0.0"]
    dataset_id: Literal[
        "realistic-internal-demo-v1",
        "realistic-internal-demo-v2",
        "realistic-internal-demo-v3",
    ]
    tenant_slug: Literal["csight"]
    selection: DemoSelection
    boundaries: DemoBoundaries
    narrative_contract: DemoNarrativeContract | None = None
    cases: tuple[DemoCase, ...]

    @model_validator(mode="after")
    def require_frozen_selection(self) -> Self:
        version_by_dataset = {
            DATASET_ID_V1: "1.0.0",
            DATASET_ID_V2: "2.0.0",
            DATASET_ID_V3: "3.0.0",
        }
        expected_schema_version = version_by_dataset[self.dataset_id]
        if self.schema_version != expected_schema_version:
            raise ValueError("schema_version and dataset_id must identify the same demo version")
        has_ecommerce_narrative = self.dataset_id in {DATASET_ID_V2, DATASET_ID_V3}
        if has_ecommerce_narrative != (self.narrative_contract is not None):
            raise ValueError("ecommerce demo datasets require the narrative contract")
        if len(self.cases) != 10:
            raise ValueError("realistic demo manifest must contain exactly ten cases")
        defect_ranks = tuple(
            item.source.rank
            for item in self.cases
            if item.source.kind == "TOP100_SELECTED_CORRECT_DEFECT"
        )
        normal_ranks = tuple(
            item.source.rank
            for item in self.cases
            if item.source.kind == "USER_SUPPLIED_NORMAL_REFERENCE"
        )
        expected_defect_ranks = (
            DEFECT_RANKS_V3 if self.dataset_id == DATASET_ID_V3 else DEFECT_RANKS
        )
        expected_normal_ranks = (
            NORMAL_REFERENCE_RANKS_V3
            if self.dataset_id == DATASET_ID_V3
            else NORMAL_REFERENCE_RANKS
        )
        if defect_ranks != expected_defect_ranks or normal_ranks != expected_normal_ranks:
            raise ValueError("manifest does not match the frozen 6:4 source-rank selection")
        if self.selection.defect_ranks != expected_defect_ranks:
            raise ValueError("selection.defect_ranks does not match case records")
        if self.selection.normal_reference_ranks != expected_normal_ranks:
            raise ValueError("selection.normal_reference_ranks does not match case records")
        if len({item.demo_id for item in self.cases}) != len(self.cases):
            raise ValueError("demo identifiers must be unique")
        if len({item.case_input.order_ref for item in self.cases}) != len(self.cases):
            raise ValueError("demo order references must be unique")
        expected_demo_prefix = {
            DATASET_ID_V1: "REAL-DEMO-",
            DATASET_ID_V2: "REAL-DEMO-V2-",
            DATASET_ID_V3: "REAL-DEMO-V3-",
        }[self.dataset_id]
        if any(not item.demo_id.startswith(expected_demo_prefix) for item in self.cases):
            raise ValueError("demo identifiers must stay within their dataset version")
        if has_ecommerce_narrative:
            for item in self.cases:
                if "synthetic_commerce_context" not in item.case_input.attributes:
                    raise ValueError("v2 demo Cases require a synthetic commerce context")
                message = item.case_input.customer_message
                sentence_count = sum(message.count(mark) for mark in (".", "?", "!"))
                if sentence_count < 3 or sentence_count > 5 or len(message) < 120:
                    raise ValueError(
                        "ecommerce inquiries must contain three to five substantive sentences"
                    )
                lowered = message.lower()
                if any(name in lowered for name in PROHIBITED_COMMERCE_NAMES):
                    raise ValueError(
                        "ecommerce inquiries cannot name or impersonate a real company"
                    )
                if EMAIL_PATTERN.search(message) or PHONE_PATTERN.search(message):
                    raise ValueError("ecommerce inquiries cannot contain email or phone PII")
                observation = item.case_input.attributes.get("demo_image_observation")
                if not isinstance(observation, str) or len(observation.strip()) < 20:
                    raise ValueError("ecommerce inquiries require a substantive image observation")
                if (
                    item.case_input.attributes.get("demo_claim_boundary")
                    != "CUSTOMER_STATEMENT_ONLY_FOR_NON_VISIBLE_FACTS"
                ):
                    raise ValueError(
                        "ecommerce inquiries require the customer-statement claim boundary"
                    )
        return self


class DemoExpansionOverrides(BaseModel):
    model_config = _MODEL_CONFIG

    order_ref: str = Field(min_length=1, max_length=200)
    product_ref: str = Field(min_length=1, max_length=200)
    customer_message: str = Field(min_length=120, max_length=20_000)
    requested_action: str
    product_display_name: str = Field(min_length=2, max_length=160)
    synthetic_sku: str = Field(pattern=r"^CS-DEMO-[A-Z0-9-]{3,40}$")
    unit_price: Decimal = Field(gt=0)
    shipping_fee: Decimal = Field(ge=0)
    discount_amount: Decimal = Field(ge=0)
    image_observation: str = Field(min_length=20, max_length=500)
    declared_safety_risk: bool
    external_action_input_mode: Literal[
        "NONE",
        "QUANTITY_AND_INHERITED_ADDRESS",
        "REFUND_PAID_AMOUNT",
    ]

    @model_validator(mode="after")
    def require_expansion_business_input(self) -> Self:
        if self.requested_action not in REQUESTED_ACTIONS:
            raise ValueError("expansion requested_action is unsupported")
        if self.discount_amount > self.unit_price + self.shipping_fee:
            raise ValueError("expansion discount cannot exceed the pre-discount total")
        if (self.requested_action == "REFUND") != (
            self.external_action_input_mode == "REFUND_PAID_AMOUNT"
        ):
            raise ValueError("refund expansion requires explicit paid-amount input mode")
        return self


class DemoExpansionCase(BaseModel):
    model_config = _MODEL_CONFIG

    demo_id: str = Field(pattern=r"^REAL-DEMO-V3-(DEFECT|NORMAL)-[0-9]{2}$")
    base_demo_id: str = Field(pattern=r"^REAL-DEMO-V2-(DEFECT|NORMAL)-[0-9]{2}$")
    source: DemoSource
    overrides: DemoExpansionOverrides


class DemoExpansionManifest(BaseModel):
    model_config = _MODEL_CONFIG

    schema_version: Literal["3.0.0"]
    dataset_id: Literal["realistic-internal-demo-v3"]
    base_dataset_id: Literal["realistic-internal-demo-v2"]
    base_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_slug: Literal["csight"]
    selection: DemoSelection
    boundaries: DemoBoundaries
    narrative_contract: DemoNarrativeContract
    cases: tuple[DemoExpansionCase, ...]

    @model_validator(mode="after")
    def require_expansion_pack(self) -> Self:
        if self.narrative_contract.revision != "CLOSED_SET_EXPANSION_R3":
            raise ValueError("expansion narrative revision drifted")
        if len(self.cases) != 10:
            raise ValueError("expansion pack must contain exactly ten cases")
        if len({item.demo_id for item in self.cases}) != len(self.cases):
            raise ValueError("expansion demo identifiers must be unique")
        if len({item.base_demo_id for item in self.cases}) != len(self.cases):
            raise ValueError("expansion base templates must be used once")
        return self


@dataclass(frozen=True, slots=True)
class ActorIdentity:
    tenant_id: str
    user_id: str
    email: str
    roles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolvedDemoSource:
    definition: DemoCase
    path: Path
    capture_id: str
    image_sha256: str
    source_metadata: Mapping[str, object]


def _materialize_expansion_manifest(expansion: DemoExpansionManifest) -> DemoManifest:
    if (
        hashlib.sha256(DEFAULT_MANIFEST_V2.read_bytes()).hexdigest()
        != expansion.base_manifest_sha256
    ):
        raise RealisticDemoSeedFailure("v3 expansion base manifest hash drifted")
    try:
        base = DemoManifest.model_validate_json(DEFAULT_MANIFEST_V2.read_text(encoding="utf-8"))
    except ValidationError as error:
        raise RealisticDemoSeedFailure("v3 expansion base manifest is invalid") from error
    base_cases = {item.demo_id: item for item in base.cases}
    materialized: list[DemoCase] = []
    for item in expansion.cases:
        template = base_cases.get(item.base_demo_id)
        if template is None or template.source.kind != item.source.kind:
            raise RealisticDemoSeedFailure("v3 expansion template kind is invalid")
        overrides = item.overrides
        payload = template.case_input.model_dump(mode="json")
        attributes = cast(dict[str, object], payload["attributes"])
        context = cast(dict[str, object], attributes["synthetic_commerce_context"])
        order = cast(dict[str, object], context["order"])
        delivery = cast(dict[str, object], context["delivery"])
        paid_amount = overrides.unit_price + overrides.shipping_fee - overrides.discount_amount
        order.update(
            {
                "product_display_name": overrides.product_display_name,
                "sku": overrides.synthetic_sku,
                "quantity": 1,
                "unit_price": format(overrides.unit_price, "f"),
                "merchandise_amount": format(overrides.unit_price, "f"),
                "shipping_fee": format(overrides.shipping_fee, "f"),
                "discount_amount": format(overrides.discount_amount, "f"),
                "paid_amount": format(paid_amount, "f"),
            }
        )
        if overrides.external_action_input_mode == "QUANTITY_AND_INHERITED_ADDRESS":
            external_action_input: dict[str, object] = {
                "quantity": 1,
                "shipping_address_ref": delivery["shipping_address_ref"],
            }
        elif overrides.external_action_input_mode == "REFUND_PAID_AMOUNT":
            external_action_input = {
                "amount": format(paid_amount, "f"),
                "currency": "KRW",
            }
        else:
            external_action_input = {}
        attributes.update(
            {
                "demo_image_observation": overrides.image_observation,
                "declared_safety_risk": overrides.declared_safety_risk,
                "external_action_input": external_action_input,
            }
        )
        payload.update(
            {
                "order_ref": overrides.order_ref,
                "product_ref": overrides.product_ref,
                "customer_message": overrides.customer_message,
                "requested_action": overrides.requested_action,
                "attributes": attributes,
            }
        )
        materialized.append(
            DemoCase.model_validate(
                {
                    "demo_id": item.demo_id,
                    "source": item.source.model_dump(mode="json"),
                    "case_input": payload,
                }
            )
        )
    return DemoManifest.model_validate(
        {
            "schema_version": expansion.schema_version,
            "dataset_id": expansion.dataset_id,
            "tenant_slug": expansion.tenant_slug,
            "selection": expansion.selection.model_dump(mode="json"),
            "boundaries": expansion.boundaries.model_dump(mode="json"),
            "narrative_contract": expansion.narrative_contract.model_dump(mode="json"),
            "cases": [item.model_dump(mode="json") for item in materialized],
        }
    )


def load_manifest(path: Path) -> DemoManifest:
    """Load the committed input contract as data, never as executable instructions."""

    if path.is_symlink() or not path.is_file():
        raise RealisticDemoSeedFailure("demo manifest must be a regular non-symlink file")
    try:
        content = path.read_text(encoding="utf-8")
        raw = json.loads(content)
        if isinstance(raw, dict) and raw.get("dataset_id") == DATASET_ID_V3:
            return _materialize_expansion_manifest(DemoExpansionManifest.model_validate(raw))
        return DemoManifest.model_validate(raw)
    except (json.JSONDecodeError, ValidationError) as error:
        raise RealisticDemoSeedFailure("demo manifest failed its frozen 6:4 contract") from error


def _manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_closed_set_sources(
    manifest: DemoManifest,
    sources: Sequence[ResolvedDemoSource],
    registry: PocClosedSetRegistry,
) -> dict[str, object]:
    """Bind the closed-set registry to the frozen manifest and vetted source annotations."""

    if manifest.dataset_id != registry.dataset_id:
        raise RealisticDemoSeedFailure("closed-set registry and demo dataset do not match")
    assignments = {item.demo_id: item for item in registry.assignments}
    if set(assignments) != {item.demo_id for item in manifest.cases}:
        raise RealisticDemoSeedFailure("closed-set registry does not cover the frozen demo cases")
    for source in sources:
        definition = source.definition
        assignment = assignments[definition.demo_id]
        if (
            assignment.product_ref != definition.case_input.product_ref
            or assignment.source_kind is not PocSourceKind(definition.source.kind)
            or assignment.source_rank != definition.source.rank
            or assignment.image_sha256 != source.image_sha256
        ):
            raise RealisticDemoSeedFailure("closed-set assignment does not match source identity")
        raw_labels = source.source_metadata.get("defect_annotations_not_model_predictions", [])
        if not isinstance(raw_labels, list) or any(
            not isinstance(item, str) for item in raw_labels
        ):
            raise RealisticDemoSeedFailure("closed-set source annotations are malformed")
        if tuple(raw_labels) != assignment.source_defect_labels:
            raise RealisticDemoSeedFailure(
                "closed-set defect groups do not match the vetted source annotations"
            )
    assigned_product_classes = sorted({item.product_class.value for item in registry.assignments})
    assigned_defect_groups = sorted(
        {group.value for item in registry.assignments for group in item.defect_groups}
    )
    return {
        "schema_version": registry.schema_version,
        "registry_assignment_count": len(registry.assignments),
        "configured_product_class_count": len(registry.product_classes),
        "configured_defect_group_count": len(registry.defect_groups),
        "represented_product_classes": assigned_product_classes,
        "represented_defect_groups": assigned_defect_groups,
        "unrepresented_product_classes": sorted(
            {item.code for item in registry.product_classes} - set(assigned_product_classes)
        ),
        "unrepresented_defect_groups": sorted(
            {item.code for item in registry.defect_groups} - set(assigned_defect_groups)
        ),
    }


def default_output_for_manifest(manifest: DemoManifest) -> Path:
    """Keep versioned local reports separate even when --output is omitted."""

    if manifest.dataset_id == DATASET_ID_V2:
        return DEFAULT_OUTPUT_V2
    if manifest.dataset_id == DATASET_ID_V3:
        return DEFAULT_OUTPUT_V3
    return DEFAULT_OUTPUT_V1


def resolve_output_path(manifest: DemoManifest, requested: Path | None) -> Path:
    expected = default_output_for_manifest(manifest)
    if requested is None:
        return expected
    other_defaults = {DEFAULT_OUTPUT_V1, DEFAULT_OUTPUT_V2, DEFAULT_OUTPUT_V3} - {expected}
    if requested.resolve() in {item.resolve() for item in other_defaults}:
        raise RealisticDemoSeedFailure("a versioned demo cannot overwrite another version's report")
    return requested


def build_seed_idempotency_key(
    manifest: DemoManifest,
    definition: DemoCase,
    *,
    operation: Literal["case", "analysis", "analysis-retry-1", "analysis-retry-2"],
) -> str:
    """Derive a stable key whose namespace is the immutable dataset version."""

    if manifest.narrative_contract is None:
        return f"{manifest.dataset_id}-{operation}-{definition.demo_id.lower()}"
    revision = manifest.narrative_contract.revision.lower().replace("_", "-")
    return f"{manifest.dataset_id}-{revision}-{operation}-{definition.demo_id.lower()}"


def _require_loopback_http_url(value: str, *, label: str) -> str:
    normalized = value.rstrip("/")
    try:
        parsed = urlsplit(normalized)
        port = parsed.port
    except ValueError:
        raise RealisticDemoSeedFailure(f"{label} URL is invalid") from None
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise RealisticDemoSeedFailure(f"{label} accepts only a loopback HTTP origin")
    return normalized


def require_local_runtime(
    *,
    environment: str,
    database_url: str | None,
    core_base_url: str,
    vision_base_url: str,
) -> tuple[str, str]:
    """Reject any non-local/test execution before a state-changing API call."""

    if environment.strip().lower() not in {"local", "test"}:
        raise RealisticDemoSeedFailure("realistic demo seeding is restricted to local/test")
    if not database_url:
        raise RealisticDemoSeedFailure("DATABASE_URL is required")
    try:
        database = make_url(database_url)
    except (TypeError, ValueError):
        raise RealisticDemoSeedFailure("DATABASE_URL is invalid") from None
    if not database.drivername.startswith("postgresql") or database.host not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise RealisticDemoSeedFailure("realistic demo seeding requires loopback PostgreSQL")
    return (
        _require_loopback_http_url(core_base_url, label="Core"),
        _require_loopback_http_url(vision_base_url, label="Vision"),
    )


def resolve_actor(engine: Engine, *, tenant_slug: str, actor_email: str) -> ActorIdentity:
    normalized_email = actor_email.strip().lower()
    statement = (
        select(
            TenantModel.id.label("tenant_id"),
            TenantModel.is_active.label("tenant_active"),
            UserModel.id.label("user_id"),
            UserModel.is_active.label("user_active"),
            UserModel.email,
            RoleModel.name.label("role_name"),
        )
        .join(UserModel, UserModel.tenant_id == TenantModel.id)
        .join(
            UserRoleModel,
            and_(
                UserRoleModel.tenant_id == UserModel.tenant_id,
                UserRoleModel.user_id == UserModel.id,
            ),
        )
        .join(RoleModel, RoleModel.id == UserRoleModel.role_id)
        .where(TenantModel.slug == tenant_slug, UserModel.email == normalized_email)
        .order_by(RoleModel.name)
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    if not rows:
        raise RealisticDemoSeedFailure("the requested local demo actor does not exist")
    tenant_ids = {str(row["tenant_id"]) for row in rows}
    user_ids = {str(row["user_id"]) for row in rows}
    if len(tenant_ids) != 1 or len(user_ids) != 1:
        raise RealisticDemoSeedFailure("the local demo actor identity is ambiguous")
    if any(not bool(row["tenant_active"]) or not bool(row["user_active"]) for row in rows):
        raise RealisticDemoSeedFailure("the local demo tenant and actor must be active")
    roles = tuple(sorted({str(row["role_name"]) for row in rows}))
    if "ADMIN" not in roles:
        raise RealisticDemoSeedFailure("the local demo actor must have ADMIN")
    return ActorIdentity(
        tenant_id=next(iter(tenant_ids)),
        user_id=next(iter(user_ids)),
        email=normalized_email,
        roles=roles,
    )


def issue_local_token(settings: Settings, actor: ActorIdentity) -> str:
    secret = settings.jwt_secret_key_value
    if not secret:
        raise RealisticDemoSeedFailure("JWT_SECRET_KEY is required")
    codec = PyJWTAccessTokenCodec(
        secret_key=secret,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        access_token_ttl=timedelta(minutes=min(settings.jwt_access_token_expire_minutes, 15)),
    )
    return codec.issue_token(
        subject=actor.user_id,
        tenant_id=actor.tenant_id,
        roles=actor.roles,
    )


def resolve_demo_sources(
    manifest: DemoManifest,
    *,
    defect_package: ValidatedPackage,
    normal_reference: ValidatedNormalReference,
) -> tuple[ResolvedDemoSource, ...]:
    defects = {record.rank: record for record in defect_package.records}
    normals = {record.rank: record for record in normal_reference.images}
    resolved: list[ResolvedDemoSource] = []
    for definition in manifest.cases:
        source = definition.source
        if source.kind == "TOP100_SELECTED_CORRECT_DEFECT":
            record = defects.get(source.rank)
            if (
                record is None
                or record.image_sha256 != source.image_sha256
                or record.item_material != "plastic_hard"
                or not record.major_defect
            ):
                raise RealisticDemoSeedFailure(
                    f"defect rank {source.rank} does not match the vetted source manifest"
                )
            path = defect_package.root / record.copied_file
            capture_id = record.capture_id
            source_metadata: Mapping[str, object] = {
                "material_annotation": record.item_material,
                "major_defect_annotation": record.major_defect,
                "defect_annotations_not_model_predictions": list(record.defect_types),
            }
        else:
            normal = normals.get(source.rank)
            if (
                normal is None
                or normal.image_sha256 != source.image_sha256
                or source.rank not in SAFE_INTERNAL_DEMO_RANKS
            ):
                raise RealisticDemoSeedFailure(
                    f"normal-reference rank {source.rank} does not match the vetted source"
                )
            path = normal.path
            capture_id = normal.capture_id
            source_metadata = {
                "source_grade": "USER_SUPPLIED_NORMAL_REFERENCE",
                "annotation_provenance_status": "USER_STATEMENT_ONLY",
                "normal_confirmation_supported": False,
            }
        resolved.append(
            ResolvedDemoSource(
                definition=definition,
                path=path,
                capture_id=capture_id,
                image_sha256=source.image_sha256,
                source_metadata=source_metadata,
            )
        )
    return tuple(resolved)


def _request_mapping(
    *, method: str, url: str, timeout_seconds: float, headers: Mapping[str, str] | None = None
) -> Mapping[str, object]:
    try:
        with urlopen(
            Request(
                url, headers={"Accept": "application/json", **dict(headers or {})}, method=method
            ),
            timeout=timeout_seconds,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RealisticDemoSeedFailure(f"local service returned HTTP {error.code}") from None
    except (TimeoutError, URLError):
        raise RealisticDemoSeedFailure("a required local service could not be reached") from None
    if not isinstance(payload, dict):
        raise RealisticDemoSeedFailure("a local service response was not a JSON object")
    return cast(Mapping[str, object], payload)


def validate_e3_health(vision_base_url: str) -> Mapping[str, object]:
    health = _request_mapping(
        method="GET",
        url=f"{vision_base_url}/health",
        timeout_seconds=15.0,
    )
    expected: Mapping[str, object] = {
        "status": "healthy",
        "model_name": EXPECTED_MODEL_NAME,
        "model_version": EXPECTED_MODEL_VERSION,
        "model_revision": EXPECTED_MODEL_REVISION,
        "task": VISION_TASK,
        "threshold": EXPECTED_THRESHOLD,
        "human_final_approval_required": True,
        "normal_confirmation_supported": False,
    }
    for key, value in expected.items():
        if health.get(key) != value:
            raise RealisticDemoSeedFailure(f"E3 runtime identity mismatch: {key}")
    return health


def _records(value: object, *, label: str) -> Sequence[Mapping[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RealisticDemoSeedFailure(f"Core response omitted {label}")
    return cast(Sequence[Mapping[str, object]], value)


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise RealisticDemoSeedFailure(f"Core response omitted {label}")
    return cast(Mapping[str, object], value)


def _multipart_jpeg(image_bytes: bytes, *, filename: str) -> tuple[bytes, str]:
    boundary = f"csight-realistic-demo-{uuid4().hex}"
    body = b"".join(
        (
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="evidence_type"\r\n\r\n',
            b"IMAGE\r\n",
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; '
            + f'filename="{filename}"\r\n'.encode(),
            b"Content-Type: image/jpeg\r\n\r\n",
            image_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        )
    )
    return body, boundary


def _upload_private_evidence(
    *,
    url: str,
    authorization: Mapping[str, str],
    image_bytes: bytes,
    filename: str,
) -> Mapping[str, object]:
    body, boundary = _multipart_jpeg(image_bytes, filename=filename)
    try:
        with urlopen(
            Request(
                url,
                data=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    **dict(authorization),
                },
                method="POST",
            ),
            timeout=60.0,
        ) as response:
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RealisticDemoSeedFailure(
            f"private Evidence upload returned HTTP {error.code}"
        ) from None
    except (TimeoutError, URLError):
        raise RealisticDemoSeedFailure(
            "local private Evidence upload could not be reached"
        ) from None
    if status != 201 or not isinstance(payload, dict):
        raise RealisticDemoSeedFailure("private Evidence upload response was invalid")
    return cast(Mapping[str, object], payload)


def _download_private_evidence(
    *,
    url: str,
    authorization: Mapping[str, str],
    max_bytes: int,
) -> bytes:
    if max_bytes <= 0:
        raise RealisticDemoSeedFailure("private Evidence read bound must be positive")
    try:
        with urlopen(
            Request(
                url,
                headers={"Accept": "image/jpeg,image/png,image/webp", **dict(authorization)},
                method="GET",
            ),
            timeout=60.0,
        ) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            payload = response.read(max_bytes + 1)
    except HTTPError as error:
        raise RealisticDemoSeedFailure(
            f"authenticated private Evidence read returned HTTP {error.code}"
        ) from None
    except (TimeoutError, URLError):
        raise RealisticDemoSeedFailure(
            "authenticated private Evidence read could not be reached"
        ) from None
    if status != 200 or content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise RealisticDemoSeedFailure("authenticated private Evidence response was invalid")
    if len(payload) > max_bytes:
        raise RealisticDemoSeedFailure("authenticated private Evidence exceeded its source bound")
    return payload


def validate_private_evidence_object(
    *,
    core_base_url: str,
    case_id: str,
    evidence_id: str,
    source: ResolvedDemoSource,
    authorization: Mapping[str, str],
) -> None:
    expected_size = source.path.stat().st_size
    content = _download_private_evidence(
        url=f"{core_base_url}/api/v1/cases/{case_id}/evidence/{evidence_id}/content",
        authorization=authorization,
        max_bytes=expected_size,
    )
    if len(content) != expected_size or not hmac.compare_digest(
        hashlib.sha256(content).hexdigest(), source.image_sha256
    ):
        raise RealisticDemoSeedFailure(
            "authenticated private Evidence content does not match the frozen source"
        )


def ensure_private_evidence(
    *,
    core_base_url: str,
    case_id: str,
    source: ResolvedDemoSource,
    authorization: Mapping[str, str],
) -> tuple[Mapping[str, object], bool]:
    _, listed = json_request(
        method="GET",
        url=f"{core_base_url}/api/v1/cases/{case_id}/evidence",
        headers=authorization,
        expected=frozenset({200}),
    )
    items = _records(listed.get("items"), label="Evidence items")
    if items:
        if len(items) != 1:
            raise RealisticDemoSeedFailure("a dedicated demo Case has unexpected Evidence rows")
        existing = items[0]
        if (
            existing.get("sha256") != source.image_sha256
            or existing.get("upload_status") != "AVAILABLE"
            or existing.get("evidence_type") != "IMAGE"
        ):
            raise RealisticDemoSeedFailure(
                "existing demo Evidence does not match the frozen source"
            )
        evidence_id = required_string(existing, "evidence_id")
        validate_private_evidence_object(
            core_base_url=core_base_url,
            case_id=case_id,
            evidence_id=evidence_id,
            source=source,
            authorization=authorization,
        )
        return existing, True

    uploaded = _upload_private_evidence(
        url=f"{core_base_url}/api/v1/cases/{case_id}/evidence",
        authorization=authorization,
        image_bytes=source.path.read_bytes(),
        filename=f"{source.definition.demo_id.lower()}.jpg",
    )
    if (
        uploaded.get("sha256") != source.image_sha256
        or uploaded.get("upload_status") != "AVAILABLE"
    ):
        raise RealisticDemoSeedFailure("Core Evidence SHA/status does not match the source")
    validate_private_evidence_object(
        core_base_url=core_base_url,
        case_id=case_id,
        evidence_id=required_string(uploaded, "evidence_id"),
        source=source,
        authorization=authorization,
    )
    return uploaded, False


def validate_core_vision_result(
    result: Mapping[str, object], *, expected_outcome: str
) -> tuple[float, str]:
    expected_identity: Mapping[str, object] = {
        "provider_name": "remote_vision",
        "model_name": EXPECTED_MODEL_NAME,
        "model_version": EXPECTED_MODEL_VERSION,
        "model_revision": EXPECTED_MODEL_REVISION,
        "taxonomy_version": "csight-any-defect-assessment-v1",
        "threshold_version": "1.0",
        "preprocess_version": "1.0",
        "postprocess_version": "sigmoid-any-defect-v1",
    }
    for key, value in expected_identity.items():
        if result.get(key) != value:
            raise RealisticDemoSeedFailure(f"Core-persisted E3 identity mismatch: {key}")
    detections = _records(result.get("detections"), label="Vision detections")
    if detections:
        raise RealisticDemoSeedFailure("binary E3 result invented localized detections")
    assessment = _mapping(result.get("image_assessment"), label="image_assessment")
    score = assessment.get("score")
    threshold = assessment.get("threshold")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise RealisticDemoSeedFailure("Core-persisted E3 score is invalid")
    normalized_score = float(score)
    if not math.isfinite(normalized_score) or not 0.0 <= normalized_score <= 1.0:
        raise RealisticDemoSeedFailure("Core-persisted E3 score is outside [0, 1]")
    if (
        threshold != EXPECTED_THRESHOLD
        or assessment.get("assessment_type") != "ANY_DEFECT"
        or assessment.get("threshold_operator") != "GREATER_THAN_OR_EQUAL"
    ):
        raise RealisticDemoSeedFailure("Core-persisted E3 assessment contract drifted")
    derived_outcome = (
        "HIGH_CONFIDENCE_DEFECT_CANDIDATE"
        if normalized_score >= EXPECTED_THRESHOLD
        else "BELOW_HIGH_CONFIDENCE_THRESHOLD"
    )
    outcome = assessment.get("outcome")
    if outcome != derived_outcome or outcome != expected_outcome:
        raise RealisticDemoSeedFailure("Core E3 outcome does not match score/source expectation")
    return normalized_score, cast(str, outcome)


def _wait_for_analysis(
    *,
    core_base_url: str,
    case_id: str,
    analysis_run_id: str,
    authorization: Mapping[str, str],
    timeout_seconds: float,
) -> Mapping[str, object]:
    deadline = time.monotonic() + timeout_seconds
    detail: Mapping[str, object] = {}
    while time.monotonic() < deadline:
        _, detail = json_request(
            method="GET",
            url=(f"{core_base_url}/api/v1/cases/{case_id}/analysis-runs/{analysis_run_id}"),
            headers=authorization,
            expected=frozenset({200}),
        )
        run = _mapping(detail.get("run"), label="Analysis run")
        status = run.get("status")
        if status in TERMINAL_ANALYSIS_STATUSES:
            return detail
        time.sleep(0.5)
    raise RealisticDemoSeedFailure("multimodal analysis did not finish before timeout")


def read_case_boundary_counts(engine: Engine, *, tenant_id: str, case_id: str) -> Mapping[str, int]:
    """Read policy/review/action state without mutating or requiring it to be empty."""

    tenant_uuid = UUID(tenant_id)
    case_uuid = UUID(case_id)
    count_statements = (
        (
            "policy_retrieval_runs",
            select(func.count())
            .select_from(PolicyRetrievalRunModel)
            .where(
                PolicyRetrievalRunModel.tenant_id == tenant_uuid,
                PolicyRetrievalRunModel.case_id == case_uuid,
            ),
        ),
        (
            "grounded_explanation_runs",
            select(func.count())
            .select_from(GroundedExplanationRunModel)
            .where(
                GroundedExplanationRunModel.tenant_id == tenant_uuid,
                GroundedExplanationRunModel.case_id == case_uuid,
            ),
        ),
        (
            "policy_evaluation_runs",
            select(func.count())
            .select_from(PolicyEvaluationRunModel)
            .where(
                PolicyEvaluationRunModel.tenant_id == tenant_uuid,
                PolicyEvaluationRunModel.case_id == case_uuid,
            ),
        ),
        (
            "human_review_tasks",
            select(func.count())
            .select_from(HumanReviewTaskModel)
            .where(
                HumanReviewTaskModel.tenant_id == tenant_uuid,
                HumanReviewTaskModel.case_id == case_uuid,
            ),
        ),
        (
            "case_resolutions",
            select(func.count())
            .select_from(CaseResolutionModel)
            .where(
                CaseResolutionModel.tenant_id == tenant_uuid,
                CaseResolutionModel.case_id == case_uuid,
            ),
        ),
        (
            "external_action_intents",
            select(func.count())
            .select_from(ExternalActionIntentModel)
            .where(
                ExternalActionIntentModel.tenant_id == tenant_uuid,
                ExternalActionIntentModel.case_id == case_uuid,
            ),
        ),
        (
            "external_action_simulation_attempts",
            select(func.count())
            .select_from(ExternalActionSimulationAttemptModel)
            .where(
                ExternalActionSimulationAttemptModel.tenant_id == tenant_uuid,
                ExternalActionSimulationAttemptModel.case_id == case_uuid,
            ),
        ),
        (
            "external_action_simulation_results",
            select(func.count())
            .select_from(ExternalActionSimulationResultModel)
            .where(
                ExternalActionSimulationResultModel.tenant_id == tenant_uuid,
                ExternalActionSimulationResultModel.case_id == case_uuid,
            ),
        ),
    )
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for label, statement in count_statements:
            counts[label] = int(connection.scalar(statement) or 0)

        decision_count = connection.scalar(
            select(func.count())
            .select_from(HumanReviewDecisionModel)
            .join(
                HumanReviewTaskModel,
                and_(
                    HumanReviewTaskModel.tenant_id == HumanReviewDecisionModel.tenant_id,
                    HumanReviewTaskModel.id == HumanReviewDecisionModel.review_task_id,
                ),
            )
            .where(
                HumanReviewTaskModel.tenant_id == tenant_uuid,
                HumanReviewTaskModel.case_id == case_uuid,
            )
        )
        counts["human_review_decisions"] = int(decision_count or 0)
    return counts


def validate_boundary_preservation(
    *, before: Mapping[str, int], after: Mapping[str, int], newly_created: bool
) -> None:
    if set(before) != set(BOUNDARY_COUNT_KEYS) or set(after) != set(BOUNDARY_COUNT_KEYS):
        raise RealisticDemoSeedFailure("workflow boundary count schema is incomplete")
    if any(value < 0 for value in (*before.values(), *after.values())):
        raise RealisticDemoSeedFailure("workflow boundary counts cannot be negative")
    if newly_created and any(before.values()):
        raise RealisticDemoSeedFailure("a newly created demo Case already has workflow rows")
    if dict(after) != dict(before):
        raise RealisticDemoSeedFailure(
            "workflow rows changed while the seed was running; attribution is unsafe"
        )


def _canonical_hash(value: Mapping[str, object]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def build_case_attributes(manifest: DemoManifest, source: ResolvedDemoSource) -> dict[str, object]:
    definition = source.definition
    attributes = dict(definition.case_input.attributes)
    provenance_version = {
        DATASET_ID_V1: "1.0",
        DATASET_ID_V2: "2.0",
        DATASET_ID_V3: "3.0",
    }[manifest.dataset_id]
    scenario_scope = {
        DATASET_ID_V1: "INTERNAL_CURATED_6_DEFECT_4_BELOW_THRESHOLD",
        DATASET_ID_V2: "INTERNAL_CURATED_ECOMMERCE_INQUIRY_6_DEFECT_4_BELOW_THRESHOLD",
        DATASET_ID_V3: "INTERNAL_CURATED_ECOMMERCE_EXPANSION_12_DEFECT_8_REFERENCE_TOTAL",
    }[manifest.dataset_id]
    attributes["realistic_demo"] = {
        "schema_version": provenance_version,
        "scenario_scope": scenario_scope,
        "dataset_id": manifest.dataset_id,
        "narrative_revision": (
            manifest.narrative_contract.revision
            if manifest.narrative_contract is not None
            else "FROZEN_V1"
        ),
        "demo_id": definition.demo_id,
        "source_kind": definition.source.kind,
        "source_rank": definition.source.rank,
        "source_image_sha256": source.image_sha256,
        "source_grade": definition.source.source_grade,
        "rights_status": definition.source.rights_status,
        "selection_bias": definition.source.selection_bias,
        "policy_input_linkage": "NOT_LINKED_TO_POLICY_INPUT",
        "final_decision_owner": "AUTHENTICATED_HUMAN_ONLY",
        "normal_confirmation_supported": False,
    }
    return attributes


def allow_partial_vision_seed(
    *, execution_mode: str, allow_partial_multimodal: bool, status: object
) -> bool:
    """Keep a failed legacy text stage visible during opt-in SHADOW image loading."""
    if allow_partial_multimodal and execution_mode != "SHADOW":
        raise RealisticDemoSeedFailure("partial multimodal loading requires SHADOW mode")
    return allow_partial_multimodal and status == "PARTIAL_SUCCESS"


def seed_realistic_demo(
    *,
    manifest: DemoManifest,
    sources: Sequence[ResolvedDemoSource],
    manifest_sha256: str,
    defect_package: ValidatedPackage,
    normal_reference: ValidatedNormalReference,
    core_base_url: str,
    e3_health: Mapping[str, object],
    authorization: Mapping[str, str],
    actor: ActorIdentity,
    engine: Engine,
    timeout_seconds: float,
    closed_set_registry: PocClosedSetRegistry | None = None,
    closed_set_registry_sha256: str | None = None,
    execution_mode: Literal["PRIMARY", "SHADOW"] = "PRIMARY",
    pipeline_version: Literal["1.0.0"] = "1.0.0",
    allow_partial_multimodal: bool = False,
) -> dict[str, object]:
    allow_partial_vision_seed(
        execution_mode=execution_mode,
        allow_partial_multimodal=allow_partial_multimodal,
        status=None,
    )
    seeded: list[Mapping[str, object]] = []
    created_cases = 0
    uploaded_evidence = 0
    created_analysis_cases = 0
    created_analysis_runs = 0
    boundary_totals_before = {key: 0 for key in BOUNDARY_COUNT_KEYS}
    boundary_totals_after = {key: 0 for key in BOUNDARY_COUNT_KEYS}
    closed_set_assignments = (
        {item.demo_id: item for item in closed_set_registry.assignments}
        if closed_set_registry is not None
        else {}
    )
    for source in sources:
        definition = source.definition
        case_input = definition.case_input
        attributes = build_case_attributes(manifest, source)
        case_status, created = json_request(
            method="POST",
            url=f"{core_base_url}/api/v1/cases",
            headers={
                **authorization,
                "Idempotency-Key": build_seed_idempotency_key(
                    manifest,
                    definition,
                    operation="case",
                ),
            },
            body={
                "order_ref": case_input.order_ref,
                "product_ref": case_input.product_ref,
                "customer_message": case_input.customer_message,
                "requested_action": case_input.requested_action,
                "attributes": attributes,
            },
            expected=frozenset({200, 201}),
        )
        created_cases += case_status == 201
        case_id = required_string(created, "case_id")
        boundary_counts_before = read_case_boundary_counts(
            engine,
            tenant_id=actor.tenant_id,
            case_id=case_id,
        )
        if case_status == 201 and any(boundary_counts_before.values()):
            raise RealisticDemoSeedFailure(
                "a new demo Case did not start at the Vision-only boundary"
            )
        evidence, evidence_replayed = ensure_private_evidence(
            core_base_url=core_base_url,
            case_id=case_id,
            source=source,
            authorization=authorization,
        )
        uploaded_evidence += not evidence_replayed
        evidence_id = required_string(evidence, "evidence_id")
        detail: Mapping[str, object] = {}
        analysis_run_id = ""
        analysis_status = 0
        analysis_created_for_case = False
        operations = ("analysis", "analysis-retry-1", "analysis-retry-2")
        for attempt_index, operation in enumerate(operations):
            analysis_status, started = json_request(
                method="POST",
                url=f"{core_base_url}/api/v1/cases/{case_id}/analysis-runs",
                headers={
                    **authorization,
                    "Idempotency-Key": build_seed_idempotency_key(
                        manifest,
                        definition,
                        operation=operation,
                    ),
                },
                body={
                    "pipeline": "product_defect_multimodal_analysis",
                    "pipeline_version": pipeline_version,
                    "execution_mode": execution_mode,
                },
                expected=frozenset({200, 202}),
            )
            created_analysis_runs += analysis_status == 202
            analysis_created_for_case = analysis_created_for_case or analysis_status == 202
            analysis_run_id = required_string(started, "analysis_run_id")
            detail = _wait_for_analysis(
                core_base_url=core_base_url,
                case_id=case_id,
                analysis_run_id=analysis_run_id,
                authorization=authorization,
                timeout_seconds=timeout_seconds,
            )
            run = _mapping(detail.get("run"), label="Analysis run")
            status = run.get("status")
            if execution_mode == "SHADOW" and run.get("execution_mode") != "SHADOW":
                raise RealisticDemoSeedFailure("seeded analysis did not retain SHADOW mode")
            if status == "SUCCEEDED":
                break
            if allow_partial_vision_seed(
                execution_mode=execution_mode,
                allow_partial_multimodal=allow_partial_multimodal,
                status=status,
            ):
                break
            if attempt_index == len(operations) - 1:
                raise RealisticDemoSeedFailure(
                    f"multimodal analysis finished as {status} after two fixed retries"
                )
        created_analysis_cases += analysis_created_for_case
        vision_records = _records(detail.get("vision_results"), label="Vision results")
        if len(vision_records) != 1:
            raise RealisticDemoSeedFailure("Core did not persist exactly one Vision result")
        result = _mapping(vision_records[0].get("result"), label="Vision result")
        score, outcome = validate_core_vision_result(
            result,
            expected_outcome=definition.source.expected_e3_outcome,
        )
        closed_set_admission = None
        assignment = closed_set_assignments.get(definition.demo_id)
        if closed_set_registry is not None:
            if assignment is None:
                raise RealisticDemoSeedFailure("closed-set assignment disappeared during seeding")
            closed_set_admission = assess_poc_admission(
                assignment,
                score=score,
                outcome=outcome,
                gate_version=closed_set_registry.schema_version,
            )
        boundary_counts_after = read_case_boundary_counts(
            engine,
            tenant_id=actor.tenant_id,
            case_id=case_id,
        )
        validate_boundary_preservation(
            before=boundary_counts_before,
            after=boundary_counts_after,
            newly_created=case_status == 201,
        )
        for key in BOUNDARY_COUNT_KEYS:
            boundary_totals_before[key] += boundary_counts_before[key]
            boundary_totals_after[key] += boundary_counts_after[key]
        seeded.append(
            {
                "demo_id": definition.demo_id,
                "source_kind": definition.source.kind,
                "source_rank": definition.source.rank,
                "source_grade": definition.source.source_grade,
                "source_capture_id": source.capture_id,
                "source_image_sha256": source.image_sha256,
                "source_metadata": dict(source.source_metadata),
                "case_id": case_id,
                "evidence_id": evidence_id,
                "analysis_run_id": analysis_run_id,
                "console_path": f"/cases/{case_id}",
                "case_replayed": case_status == 200,
                "evidence_replayed": evidence_replayed,
                "analysis_replayed": analysis_status == 200,
                "run_status": run.get("status"),
                "score": score,
                "threshold": EXPECTED_THRESHOLD,
                "outcome": outcome,
                "poc_closed_set": (
                    {
                        "schema_version": closed_set_admission.gate_version,
                        "product_class": assignment.product_class.value,
                        "defect_groups": [group.value for group in assignment.defect_groups],
                        "source_defect_labels_not_model_predictions": list(
                            assignment.source_defect_labels
                        ),
                        "admission_tier": closed_set_admission.tier,
                        "admitted": closed_set_admission.admitted,
                    }
                    if assignment is not None and closed_set_admission is not None
                    else None
                ),
                "localized_detection_count": 0,
                "policy_decision_action_counts_before": dict(boundary_counts_before),
                "policy_decision_action_counts_after": dict(boundary_counts_after),
                "workflow_row_counts_unchanged_during_seed": True,
            }
        )

    report: dict[str, object] = {
        "schema_version": manifest.schema_version,
        "report_kind": "REALISTIC_INTERNAL_DEMO_SEED",
        "analysis_execution_mode": execution_mode,
        "analysis_pipeline_version": pipeline_version,
        "multimodal_analysis_status": (
            "PASS" if all(item["run_status"] == "SUCCEEDED" for item in seeded) else "FAIL"
        ),
        "partial_multimodal_count": sum(item["run_status"] == "PARTIAL_SUCCESS" for item in seeded),
        "created_at": datetime.now(UTC).isoformat(),
        "verdict": (
            "REALISTIC_INTERNAL_DEMO_LOADED_WITH_PARTIAL_ANALYSIS"
            if any(item["run_status"] != "SUCCEEDED" for item in seeded)
            else "REALISTIC_INTERNAL_DEMO_20_CASES_TOTAL_READY"
            if manifest.dataset_id == DATASET_ID_V3
            else "REALISTIC_INTERNAL_DEMO_10_CASES_READY"
        ),
        "pack_case_count": len(seeded),
        "cumulative_active_demo_case_count": (
            20 if manifest.dataset_id == DATASET_ID_V3 else len(seeded)
        ),
        "dataset_id": manifest.dataset_id,
        "tenant_slug": manifest.tenant_slug,
        "actor": {
            "user_id": actor.user_id,
            "roles": list(actor.roles),
            "plaintext_credentials_used": False,
            "access_token_persisted": False,
        },
        "manifest_sha256": manifest_sha256,
        "source_boundaries": {
            "defect_package_content_tree_sha256": defect_package.content_tree_sha256,
            "normal_reference_content_tree_sha256": normal_reference.content_tree_sha256,
            "defect_count": 6,
            "normal_reference_count": 4,
            "curated_ratio": "6:4",
            "rights_status": "INTERNAL_RESTRICTED_PROVENANCE_UNVERIFIED",
            "annotation_provenance": {
                "defect": "SOURCE_MANIFEST_SELECTED_CORRECT_ONLY",
                "normal_reference": "USER_STATEMENT_ONLY",
            },
            "selection_bias": [
                "DEFECT_POSITIVE_ONLY_CORRECT_ONLY_HIGH_CONFIDENCE",
                "NORMAL_LOW_SCORE_WITHIN_PIXEL_REVIEWED_INTERNAL_ALLOWLIST",
            ],
            "raw_images_copied_to_repository_or_web_static": False,
        },
        "poc_closed_set": (
            {
                "schema_version": closed_set_registry.schema_version,
                "registry_sha256": closed_set_registry_sha256,
                "runtime_threshold_unchanged": closed_set_registry.e3_runtime_threshold,
                "defect_admission_min_score": closed_set_registry.defect_admission_min_score,
                "reference_admission_max_score": closed_set_registry.reference_admission_max_score,
                "gray_zone_disposition": closed_set_registry.gray_zone_disposition,
                "qwen_product_role": closed_set_registry.qwen_product_role,
                "admitted_count": len(seeded),
                "performance_evaluation_supported": False,
            }
            if closed_set_registry is not None
            else None
        ),
        "e3_runtime": {
            "model_name": e3_health.get("model_name"),
            "model_version": e3_health.get("model_version"),
            "model_revision": e3_health.get("model_revision"),
            "task": e3_health.get("task"),
            "threshold": e3_health.get("threshold"),
            "normal_confirmation_supported": False,
        },
        "idempotency": {
            "created_case_count": created_cases,
            "replayed_case_count": len(seeded) - created_cases,
            "uploaded_evidence_count": uploaded_evidence,
            "reused_evidence_count": len(seeded) - uploaded_evidence,
            "created_analysis_count": created_analysis_cases,
            "replayed_analysis_count": len(seeded) - created_analysis_cases,
            "created_analysis_run_count": created_analysis_runs,
        },
        "claim_boundary": {
            "allowed": [
                "real E3/Core integration on ten curated internal demo images",
                "realistic fictional Korean customer inquiry presentation",
                "private Evidence and append-only analysis replay evidence",
            ],
            "not_supported": [
                "normal confirmation from a below-threshold score",
                "accuracy, recall, specificity, false-positive rate, or calibration",
                "defect type or localization prediction",
                "product qualification, customer performance, ROI, or public redistribution",
            ],
        },
        "safety": {
            "policy_input_linkage": "NOT_LINKED_TO_POLICY_INPUT",
            "human_final_decision_required": True,
            "authenticated_private_evidence_integrity_verified_count": len(seeded),
            "workflow_counts_before": boundary_totals_before,
            "workflow_counts_after": boundary_totals_after,
            "seed_created_policy_review_decision_action_rows": 0,
            "live_external_action_performed": False,
            "below_threshold_means_normal": False,
        },
        "cases": seeded,
    }
    report["report_sha256"] = _canonical_hash(report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top100-source", type=Path, required=True)
    parser.add_argument("--normal-source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--closed-set-registry", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--core-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--vision-base-url", default="http://127.0.0.1:8093")
    parser.add_argument("--actor-email", default="csight@csight.demo")
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--execution-mode", choices=("PRIMARY", "SHADOW"), default="PRIMARY")
    parser.add_argument("--pipeline-version", choices=("1.0.0",), default="1.0.0")
    parser.add_argument("--allow-partial-multimodal", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if arguments.timeout_seconds <= 0:
            raise RealisticDemoSeedFailure("timeout-seconds must be positive")
        settings = Settings(
            _env_file=arguments.env_file  # pyright: ignore[reportCallIssue]
        )
        core_base_url, vision_base_url = require_local_runtime(
            environment=settings.environment,
            database_url=settings.database_url_value,
            core_base_url=arguments.core_base_url,
            vision_base_url=arguments.vision_base_url,
        )
        manifest = load_manifest(arguments.manifest)
        output_path = resolve_output_path(manifest, arguments.output)
        defect_package = validate_package(arguments.top100_source)
        normal_reference = validate_normal_reference(arguments.normal_source)
        sources = resolve_demo_sources(
            manifest,
            defect_package=defect_package,
            normal_reference=normal_reference,
        )
        closed_set_registry = None
        closed_set_registry_path = arguments.closed_set_registry
        if manifest.dataset_id in {DATASET_ID_V2, DATASET_ID_V3}:
            closed_set_registry_path = closed_set_registry_path or (
                DEFAULT_CLOSED_SET_REGISTRY_V2
                if manifest.dataset_id == DATASET_ID_V3
                else DEFAULT_CLOSED_SET_REGISTRY
            )
            closed_set_registry = load_poc_closed_set_registry(closed_set_registry_path)
            validate_closed_set_sources(manifest, sources, closed_set_registry)
        elif closed_set_registry_path is not None:
            raise RealisticDemoSeedFailure(
                "closed-set registry is supported only by ecommerce demos"
            )
        e3_health = validate_e3_health(vision_base_url)
        engine = get_engine(settings)
        actor = resolve_actor(
            engine,
            tenant_slug=manifest.tenant_slug,
            actor_email=arguments.actor_email,
        )
        token = issue_local_token(settings, actor)
        authorization = {"Authorization": f"Bearer {token}"}
        _, current_user = json_request(
            method="GET",
            url=f"{core_base_url}/api/v1/auth/me",
            headers=authorization,
            expected=frozenset({200}),
        )
        if (
            current_user.get("user_id") != actor.user_id
            or current_user.get("tenant_id") != actor.tenant_id
            or "ADMIN" not in _string_records(current_user.get("roles"), label="roles")
        ):
            raise RealisticDemoSeedFailure("Core did not rehydrate the local demo ADMIN")
        report = seed_realistic_demo(
            manifest=manifest,
            sources=sources,
            manifest_sha256=_manifest_sha256(arguments.manifest),
            defect_package=defect_package,
            normal_reference=normal_reference,
            core_base_url=core_base_url,
            e3_health=e3_health,
            authorization=authorization,
            actor=actor,
            engine=engine,
            timeout_seconds=arguments.timeout_seconds,
            execution_mode=arguments.execution_mode,
            pipeline_version=arguments.pipeline_version,
            allow_partial_multimodal=arguments.allow_partial_multimodal,
            closed_set_registry=closed_set_registry,
            closed_set_registry_sha256=(
                _manifest_sha256(closed_set_registry_path)
                if closed_set_registry_path is not None
                else None
            ),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "verdict": report["verdict"],
                    "report": str(output_path),
                    "report_sha256": report["report_sha256"],
                    "case_count": len(cast(Sequence[object], report["cases"])),
                    "idempotency": report["idempotency"],
                    "safety": report["safety"],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        ValidationError,
        ScenarioVisionSmokeFailure,
        Top100ReplayFailure,
        NormalReferenceFailure,
        PocClosedSetError,
        RealisticDemoSeedFailure,
    ) as error:
        print(f"Realistic demo seed failed: {error}", file=sys.stderr)
        return 1


def _string_records(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RealisticDemoSeedFailure(f"Core response omitted {label}")
    return tuple(cast(list[str], value))


if __name__ == "__main__":
    raise SystemExit(main())
