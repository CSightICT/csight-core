"""Seed the five fictional hard-plastic PoC cases into the local CSight console."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from scripts.smoke_scenario_vision import (
    ScenarioVisionSmokeFailure,
    env_values,
    json_request,
    required_string,
    synthetic_pump_image,
    upload_image,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "evaluation/scenario_poc_hard_plastic_v1/cases.jsonl"


class ScenarioSeedFailure(RuntimeError):
    """A safe local scenario-seeding failure."""


def _load_demo_cases(path: Path) -> tuple[Mapping[str, object], ...]:
    records: list[Mapping[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ScenarioSeedFailure(f"case line {line_number} is not a JSON object")
        if value.get("split") == "demo":
            records.append(cast(Mapping[str, object], value))
    if len(records) != 5:
        raise ScenarioSeedFailure("the scenario pack must contain exactly five demo cases")
    return tuple(records)


def _case_input(record: Mapping[str, object]) -> Mapping[str, object]:
    value = record.get("case_input")
    if not isinstance(value, dict):
        raise ScenarioSeedFailure("a demo record omitted case_input")
    return cast(Mapping[str, object], value)


def seed(
    *,
    base_url: str,
    reviewer_password: str,
    cases_path: Path,
) -> Mapping[str, object]:
    _, token_response = json_request(
        method="POST",
        url=f"{base_url}/api/v1/auth/token",
        body={
            "tenant_slug": "csight-demo",
            "email": "reviewer@csight.demo",
            "password": reviewer_password,
        },
        expected=frozenset({200}),
    )
    authorization = {"Authorization": f"Bearer {required_string(token_response, 'access_token')}"}
    seeded: list[dict[str, object]] = []
    for record in _load_demo_cases(cases_path):
        record_id = required_string(record, "record_id")
        case_input = _case_input(record)
        source_attributes = case_input.get("attributes")
        attributes = dict(source_attributes) if isinstance(source_attributes, dict) else {}
        attributes["scenario_poc"] = {
            "record_id": record_id,
            "source_type": "SYNTHETIC_REFERENCE",
            "product_scope": "HDP-100",
        }
        _, created = json_request(
            method="POST",
            url=f"{base_url}/api/v1/cases",
            headers={
                **authorization,
                "Idempotency-Key": f"scenario-hard-plastic-v1-{record_id.lower()}",
            },
            body={
                "order_ref": str(case_input.get("order_ref", "")),
                "product_ref": str(case_input.get("product_ref", "")),
                "customer_message": str(case_input.get("customer_message", "")),
                "requested_action": str(case_input.get("declared_requested_action", "UNSPECIFIED")),
                "attributes": attributes,
            },
            expected=frozenset({200, 201}),
        )
        case_id = required_string(created, "case_id")
        _, detail = json_request(
            method="GET",
            url=f"{base_url}/api/v1/cases/{case_id}",
            headers=authorization,
            expected=frozenset({200}),
        )
        evidence = detail.get("evidence")
        if not isinstance(evidence, list):
            raise ScenarioSeedFailure("case detail omitted evidence")
        image_input = case_input.get("image_evidence")
        image_metadata = image_input if isinstance(image_input, dict) else {}
        visual_condition = str(image_metadata.get("visual_condition", ""))
        if not evidence:
            upload_image(
                url=f"{base_url}/api/v1/cases/{case_id}/evidence",
                authorization=authorization,
                image=synthetic_pump_image(
                    visible_breakage=visual_condition == "VISIBLE_DECONSTRUCTION"
                ),
                filename=f"{record_id.lower()}-synthetic-pump.png",
            )
        seeded.append(
            {
                "record_id": record_id,
                "case_id": case_id,
                "console_path": f"/cases/{case_id}",
                "image_fixture": "SYNTHETIC_PLACEHOLDER",
            }
        )
    return {
        "verdict": "FIVE_SYNTHETIC_DEMO_CASES_READY",
        "claim_boundary": "SCENARIO_FIXTURES_NOT_CUSTOMER_DATA",
        "cases": seeded,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--base-url")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        env = env_values(arguments.env_file)
        password = env.get("DEVELOPMENT_SEED_REVIEWER_PASSWORD", "")
        if len(password) < 12:
            raise ScenarioSeedFailure(
                "DEVELOPMENT_SEED_REVIEWER_PASSWORD must be configured before seeding"
            )
        port = env.get("API_PORT", "8000")
        base_url = (arguments.base_url or f"http://127.0.0.1:{port}").rstrip("/")
        if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ScenarioSeedFailure("the seed command accepts only a local API URL")
        report = seed(
            base_url=base_url,
            reviewer_password=password,
            cases_path=arguments.cases,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        ScenarioSeedFailure,
        ScenarioVisionSmokeFailure,
    ) as error:
        print(f"Scenario seed failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
