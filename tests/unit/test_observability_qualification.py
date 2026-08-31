"""Static safety contracts for the isolated observability qualification stack."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_observability_stack_is_digest_pinned_internal_and_has_no_host_ports() -> None:
    compose = yaml.safe_load(
        (ROOT / "infra/observability/compose.observability-qualification.yml").read_text()
    )
    services = compose["services"]
    for name in ("collector", "prometheus", "alertmanager"):
        assert "@sha256:" in services[name]["image"]
    assert all("ports" not in service for service in services.values())
    assert compose["networks"]["qualification"]["internal"] is True
    assert services["emitter"]["environment"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == (
        "http://collector:4318"
    )


def test_alert_rule_and_receiver_are_local_fixed_contracts() -> None:
    collector = yaml.safe_load((ROOT / "infra/observability/collector.yml").read_text())
    metric_processors = collector["service"]["pipelines"]["metrics"]["processors"]
    assert metric_processors == ["resource/metric-safety", "batch"]
    assert collector["processors"]["resource/metric-safety"]["attributes"] == [
        {"key": "service.instance.id", "action": "delete"}
    ]

    alerts = yaml.safe_load((ROOT / "infra/observability/alerts.yml").read_text())
    rule = alerts["groups"][0]["rules"][0]
    assert rule["alert"] == "CSightHttpTelemetryObserved"
    assert rule["expr"] == "sum(csight_http_server_request_count_total) >= 1"
    assert rule["labels"] == {
        "severity": "qualification",
        "receiver_scope": "local_only",
    }
    alertmanager = yaml.safe_load((ROOT / "infra/observability/alertmanager.yml").read_text())
    webhook = alertmanager["receivers"][0]["webhook_configs"][0]
    assert webhook == {
        "url": "http://receiver:8080/alerts",
        "send_resolved": True,
    }


def test_metric_label_validator_rejects_identifiers() -> None:
    module = _load_script("qualify_observability.py")
    module._assert_safe_metric_labels(  # pyright: ignore[reportPrivateUsage]
        [
            {
                "__name__": module.METRIC_NAME,
                "http_request_method": "GET",
                "http_route": "/health/live",
                "http_response_status_code_class": "2xx",
                "instance": "collector:8889",
                "job": "csight-otel-collector",
            }
        ]
    )

    try:
        module._assert_safe_metric_labels(  # pyright: ignore[reportPrivateUsage]
            [{"tenant_id": "00000000-0000-4000-8000-000000000001"}]
        )
    except RuntimeError as error:
        assert "forbidden metric label key" in str(error)
    else:
        raise AssertionError("tenant identifier label must fail closed")
