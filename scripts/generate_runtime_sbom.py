"""Generate a deterministic CycloneDX inventory from inside a runtime image."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
from pathlib import Path
from urllib.parse import quote

_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_DPKG_STATUS = Path("/var/lib/dpkg/status")


def _python_components() -> list[dict[str, object]]:
    packages: dict[tuple[str, str], dict[str, object]] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if not name or not version:
            continue
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        packages[(normalized, version)] = {
            "type": "library",
            "bom-ref": f"pkg:pypi/{quote(normalized)}@{quote(version)}",
            "name": normalized,
            "version": version,
            "purl": f"pkg:pypi/{quote(normalized)}@{quote(version)}",
            "properties": [{"name": "csight.inventory.source", "value": "python"}],
        }
    return [packages[key] for key in sorted(packages)]


def _dpkg_components(status_path: Path = _DPKG_STATUS) -> list[dict[str, object]]:
    if not status_path.is_file():
        return []
    packages: dict[tuple[str, str, str], dict[str, object]] = {}
    for stanza in status_path.read_text(encoding="utf-8", errors="strict").split("\n\n"):
        fields: dict[str, str] = {}
        for line in stanza.splitlines():
            if ": " not in line:
                continue
            key, value = line.split(": ", 1)
            fields[key] = value
        name = fields.get("Package")
        version = fields.get("Version")
        architecture = fields.get("Architecture")
        if (
            not name
            or not version
            or not architecture
            or fields.get("Status") != "install ok installed"
        ):
            continue
        purl = f"pkg:deb/debian/{quote(name)}@{quote(version)}?arch={quote(architecture)}"
        packages[(name, version, architecture)] = {
            "type": "library",
            "bom-ref": purl,
            "name": name,
            "version": version,
            "purl": purl,
            "properties": [
                {"name": "csight.inventory.source", "value": "dpkg"},
                {"name": "csight.package.architecture", "value": architecture},
            ],
        }
    return [packages[key] for key in sorted(packages)]


def build_sbom(*, runtime_image: str, runtime_image_digest: str) -> dict[str, object]:
    if not runtime_image.strip():
        raise ValueError("runtime image must not be empty")
    if not _DIGEST_PATTERN.fullmatch(runtime_image_digest):
        raise ValueError("runtime image digest must be an exact sha256 digest")
    image_ref = f"{runtime_image}@{runtime_image_digest}"
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "container",
                "bom-ref": image_ref,
                "name": runtime_image,
                "version": runtime_image_digest,
                "properties": [
                    {
                        "name": "csight.runtime.image.digest",
                        "value": runtime_image_digest,
                    },
                    {
                        "name": "csight.inventory.scope",
                        "value": "python-and-dpkg-installed-packages",
                    },
                ],
            }
        },
        "components": _python_components() + _dpkg_components(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-image", required=True)
    parser.add_argument("--runtime-image-digest", required=True)
    arguments = parser.parse_args()
    document = build_sbom(
        runtime_image=arguments.runtime_image,
        runtime_image_digest=arguments.runtime_image_digest,
    )
    print(json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
