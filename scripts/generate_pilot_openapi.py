"""Generate the pilot OpenAPI contract with signed Case intake enabled."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from app.bootstrap.settings import Settings
from app.interface.http.signed_intake_services import SignedIntakeServiceContainer
from app.main import create_app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/openapi/pilot.openapi.json"),
    )
    arguments = parser.parse_args()
    # OpenAPI generation only inspects route declarations. The placeholder is
    # never invoked and contains no tenant, actor, public key, or Secret value.
    placeholder = cast(SignedIntakeServiceContainer, cast(Any, object()))
    application = create_app(
        Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
        signed_intake_services=placeholder,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(application.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
