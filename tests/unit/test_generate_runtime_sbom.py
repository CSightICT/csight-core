from pathlib import Path

import pytest

from scripts.generate_runtime_sbom import (  # pyright: ignore[reportPrivateUsage]
    build_sbom,
    dpkg_components,
)


def test_runtime_sbom_binds_exact_image_and_inventory(tmp_path: Path) -> None:
    status = tmp_path / "status"
    status.write_text(
        "Package: zlib1g\n"
        "Status: install ok installed\n"
        "Architecture: amd64\n"
        "Version: 1:1.3\n\n"
        "Package: ignored\n"
        "Status: deinstall ok config-files\n"
        "Architecture: amd64\n"
        "Version: 1\n",
        encoding="utf-8",
    )

    components = dpkg_components(status)
    assert len(components) == 1
    assert components[0]["name"] == "zlib1g"

    digest = "sha256:" + "a" * 64
    document = build_sbom(runtime_image="example/runtime:1", runtime_image_digest=digest)
    assert document["bomFormat"] == "CycloneDX"
    metadata = document["metadata"]
    assert isinstance(metadata, dict)
    component = metadata["component"]
    assert isinstance(component, dict)
    assert component["version"] == digest
    assert document["components"]


def test_runtime_sbom_rejects_tag_only_identity() -> None:
    with pytest.raises(ValueError, match="exact sha256"):
        build_sbom(runtime_image="example/runtime:1", runtime_image_digest="latest")
