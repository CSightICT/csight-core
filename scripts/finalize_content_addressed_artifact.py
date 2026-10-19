from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for block in iter(lambda: artifact.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "finalize"))
    parser.add_argument("--allowed-root", required=True, type=Path)
    parser.add_argument("--incoming", required=True, type=Path)
    parser.add_argument("--partial", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument("--expected-bytes", required=True, type=int)
    parser.add_argument("--expected-sha256", required=True)
    return parser


def _is_beneath(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def main() -> int:
    args = _parser().parse_args()
    root = args.allowed_root
    paths = (args.incoming, args.partial, args.final)
    if not root.is_absolute() or any(not path.is_absolute() for path in paths):
        return 2
    if any(not _is_beneath(path, root) for path in paths):
        return 2
    if args.partial.parent != args.incoming:
        return 2

    if args.phase == "prepare":
        if args.incoming.exists() or args.incoming.is_symlink() or args.final.exists():
            return 2
        args.incoming.mkdir(mode=0o700, parents=False)
        print(
            json.dumps(
                {"schema": "csight_artifact_finalize/1.0.0", "status": "READY"},
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0

    if (
        not args.partial.is_file()
        or args.partial.is_symlink()
        or args.partial.stat().st_size != args.expected_bytes
        or _sha256(args.partial) != args.expected_sha256
        or args.final.exists()
        or args.final.is_symlink()
    ):
        return 2
    args.final.parent.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.replace(args.partial, args.final)
    args.final.chmod(0o600)
    args.incoming.rmdir()
    if (
        args.final.stat().st_size != args.expected_bytes
        or _sha256(args.final) != args.expected_sha256
    ):
        return 2
    print(
        json.dumps(
            {"schema": "csight_artifact_finalize/1.0.0", "status": "PASS"},
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
