"""Patch only the login route in the currently deployed CSight Web bundle.

The live image predates unrelated, uncommitted frontend work in this checkout.
This narrow overlay keeps those changes out of the running service.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

EXPECTED_BUNDLE_SHA256 = "0465672796fa7006cab3ebecc0b47a7a54e5f4e2a32fc356e42b5947ed7cbe7a"

REPLACEMENTS = (
    ("to:`/login`", "to:`/login2`"),
    (r"[/^\/login$/,`로그인`]", r"[/^\/(?:login|login2)$/,`로그인`]"),
    (
        "(0,A.jsx)(Xt,{path:`/login`,element:j((0,A.jsx)(Ti,{}))})",
        "(0,A.jsx)(Xt,{path:`/login`,element:j((0,A.jsx)(Ti,{}))}),"
        "(0,A.jsx)(Xt,{path:`/login2`,element:j((0,A.jsx)(Ti,{}))})",
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_bytes = args.bundle.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    if digest != EXPECTED_BUNDLE_SHA256:
        raise SystemExit(f"Unexpected deployed bundle SHA-256: {digest}")

    source = source_bytes.decode("utf-8")
    for old, new in REPLACEMENTS:
        if source.count(old) != 1:
            raise SystemExit(f"Expected one occurrence of {old!r}; found {source.count(old)}")
        source = source.replace(old, new, 1)

    original_assets = {
        asset.name: asset.read_text(encoding="utf-8") for asset in args.bundle.parent.glob("*.js")
    }
    if args.bundle.name not in original_assets:
        raise SystemExit("Main bundle is missing from its asset directory")
    original_assets[args.bundle.name] = source
    renamed_assets = {name: f"login2-20260929-{name}" for name in original_assets}

    index = args.index.read_text(encoding="utf-8")
    old_asset_url = f"/assets/{args.bundle.name}"
    if index.count(old_asset_url) != 1:
        raise SystemExit(f"Expected one index reference to {old_asset_url}")
    index = index.replace(old_asset_url, f"/assets/{renamed_assets[args.bundle.name]}", 1)

    assets = args.output / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for original_name, content in original_assets.items():
        for old_name, new_name in renamed_assets.items():
            content = content.replace(old_name, new_name)
        (assets / renamed_assets[original_name]).write_text(content, encoding="utf-8")
    (args.output / "index.html").write_text(index, encoding="utf-8")
    print(f"patched_bundle={renamed_assets[args.bundle.name]}")
    print(f"patched_assets={len(renamed_assets)}")


if __name__ == "__main__":
    main()
